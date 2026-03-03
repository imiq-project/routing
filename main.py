"""
main.py - Value-based personalised multimodal routing engine.
"""

import sys, os, json, argparse, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from graphhopper_client import GraphHopperClient
from agent import Agent
from personalised_router import PersonalisedRouter, ScoredRoute
from value_model import VALUE_DIMENSIONS


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--agent",     dest="agent_file", default=None)
    p.add_argument("--from",      dest="origin",     default=None)
    p.add_argument("--to",        dest="dest",       default=None)
    p.add_argument("--departure", dest="departure",  default=None)
    p.add_argument("--host",      dest="host",       default="http://localhost:8080")
    p.add_argument("--walk",      dest="max_walk",   type=int, default=500)
    p.add_argument("--pois",      dest="pois_file",  default=None,
                   help="JSON file with POI definitions for route scoring")
    p.add_argument("--poi-proximity", dest="poi_proximity", type=int, default=100,
                   help="Distance in meters for POI proximity detection (default: 100)")
    return p.parse_args()


def prompt_latlon(label):
    while True:
        raw = input(f"  {label} (lat,lon): ").strip()
        try:
            lat, lon = [float(x.strip()) for x in raw.split(",")]
            return lat, lon
        except ValueError:
            print("  Format: lat,lon  e.g. 52.1320,11.6234")


def prompt_agent():
    print("\n" + "─"*62)
    print("  AGENT PROFILE SETUP")
    print("─"*62)
    agent_id = input("  Agent ID (Enter = agent_001): ").strip() or "agent_001"
    print("\n  Value weights 0.0–1.0 (Enter = 0.0)\n")
    values = {}
    for dim in VALUE_DIMENSIONS:
        while True:
            raw = input(f"    {dim:<22}: ").strip() or "0"
            try:
                v = float(raw)
                if 0.0 <= v <= 1.0:
                    values[dim] = v
                    break
                print("    Enter 0.0 to 1.0")
            except ValueError:
                print("    Enter a number")
    print("\n  Transport availability:")
    beliefs = {
        "owns_car":      input("    Owns car?  (y/n): ").strip().lower() in ("y","yes"),
        "owns_bike":     input("    Owns bike? (y/n): ").strip().lower() in ("y","yes"),
        "has_pt_access": input("    Has PT?    (y/n): ").strip().lower() in ("y","yes"),
    }
    return Agent.from_dict({"id": agent_id, "values": values, "beliefs": beliefs}, normalise=False)


def load_agent(path):
    with open(path) as f:
        data = json.load(f)
    vals = data.get("values", {})
    all_norm = all(0.0 <= v <= 1.0 for v in vals.values())
    agent = Agent.from_dict(data, normalise=not all_norm)
    print(f"  Loaded agent '{agent.id}' from {path}")
    return agent


def fmt_dur(s):
    m = int(s // 60)
    return f"{m//60}h {m%60:02d}min" if m >= 60 else f"{m} min"

def fmt_dist(m):
    return f"{int(m)} m" if m < 1000 else f"{m/1000:.1f} km"

def fmt_time(iso):
    if not iso: return "?"
    try:
        t = iso.split("T")[-1]
        p = t.split(":")
        return f"{p[0]}:{p[1]}"
    except: return iso

def bar(score, width=10):
    n = int(round(max(0.0, min(1.0, score)) * width))
    return "█"*n + "░"*(width-n)


def print_agent_summary(agent):
    print("\n" + "="*66)
    print(f"  👤  AGENT: {agent.id}")
    print("="*66)
    print(f"\n  {'DIMENSION':<22} {'WEIGHT':>7}  IMPORTANCE")
    print(f"  {'─'*50}")
    for dim, w in sorted(agent.value_weights.items(), key=lambda x: x[1], reverse=True):
        print(f"  {dim:<22} {w:.3f}    {bar(w)}")
    print(f"\n  🚗 Car: {'✅' if agent.beliefs.get('owns_car') else '❌'}   "
          f"🚴 Bike: {'✅' if agent.beliefs.get('owns_bike') else '❌'}   "
          f"🚌 PT: {'✅' if agent.beliefs.get('has_pt_access') else '❌'}")
    print(f"  Available modes: {', '.join(agent.available_modes())}")
    top = agent.top_values(3)
    print(f"  Top priorities:  " + ",  ".join(f"{d} ({w:.2f})" for d,w in top))


def print_summary_table(results):
    print("\n" + "="*66)
    print("  📊  PERSONALISED RANKING  (highest match score first)")
    print("="*66)
    print(f"\n  {'':2} {'OPTION':<26} {'SCORE':>6}  {'TIME':<12} DISTANCE")
    print(f"  {'─'*62}")
    for sr in results:
        if sr.available:
            star = "⭐" if sr.rank == 1 else "  "
            print(f"  {star}#{sr.rank:<2} {sr.mode_label:<26} "
                  f"{sr.utility_score:>5.1f}  "
                  f"{fmt_dur(sr.route.total_duration_s):<12} "
                  f"{fmt_dist(sr.route.total_distance_m)}")
        else:
            # Show unavailable routes at the bottom
            print(f"     #{sr.rank:<2} {sr.mode_label:<26} "
                  f"{sr.utility_score:>5.1f}  "
                  f"{fmt_dur(sr.route.total_duration_s):<12} "
                  f"{fmt_dist(sr.route.total_distance_m)}"
                  f"  🚫 unavailable")


def print_route_steps(sr):
    print(f"\n  Journey steps:")
    step = 1
    for leg in sr.route.legs:
        if leg.mode == "walk":
            if leg.distance_m < 50: continue
            print(f"    Step {step}  🚶 WALK  {fmt_dist(leg.distance_m)}  ·  {fmt_dur(leg.duration_s)}")
        elif leg.mode == "bike":
            print(f"    Step {step}  🚴 BIKE  →  {leg.to_name or 'stop'}")
            print(f"             {fmt_dist(leg.distance_m)}  ·  {fmt_dur(leg.duration_s)}")
        elif leg.mode == "car":
            print(f"    Step {step}  🚗 DRIVE  →  {leg.to_name or 'stop'}")
            print(f"             {fmt_dist(leg.distance_m)}  ·  {fmt_dur(leg.duration_s)}")
            if leg.to_name and any(x in leg.to_name for x in ["Bahnhof","Station","Stop"]):
                print(f"             🅿️  Park here, continue by PT")
        elif leg.mode == "pt":
            rid = leg.route_id or ""
            rid_up = rid.upper()
            if any(x in rid_up for x in ["TRAM","STR"]):   icon,vt = "🚃","TRAM"
            elif any(x in rid_up for x in ["RE","RB","ICE","S-"]): icon,vt = "🚆","TRAIN"
            elif "FERRY" in rid_up:                          icon,vt = "⛴️","FERRY"
            else:                                            icon,vt = "🚌","BUS"
            print(f"    Step {step}  {icon} {vt}{f'  —  Line {rid}' if rid else ''}")
            print(f"             🟢 BOARD   {leg.from_name}  (Depart {fmt_time(leg.departure_time)})")
            if leg.stops and len(leg.stops) > 2:
                mid = leg.stops[1:-1]
                show = mid if len(mid) <= 4 else [mid[0], None, mid[-1]]
                for s in show:
                    if s is None:
                        print(f"                │  ··· {len(mid)-2} more stop(s) ···")
                    else:
                        t = fmt_time(s.get("arrival_time") or s.get("departure_time"))
                        print(f"                │  {s.get('stop_name','?')}  ({t})")
            print(f"             🔴 ALIGHT  {leg.to_name}  (Arrive {fmt_time(leg.arrival_time)})")
            print()
        step += 1


def print_value_breakdown(sr, agent):
    print(f"\n  Value match breakdown:")
    print(f"  {'DIMENSION':<22} {'WEIGHT':>7}  {'MODE FIT':>9}  {'CONTRIB':>8}  VERDICT")
    print(f"  {'─'*68}")
    for ds in sorted(sr.dimension_scores, key=lambda d: d.contribution, reverse=True):
        if   ds.contribution >  0.05: verdict = "✅ serves this value"
        elif ds.contribution < -0.05: verdict = "❌ conflicts"
        else:                         verdict = "➖ neutral"
        print(f"  {ds.dimension:<22} {ds.agent_weight:>7.3f}  "
              f"{ds.blended_attribute:>+9.2f}  {ds.contribution:>+8.3f}  {verdict}")
    print(f"\n  Utility score: {sr.utility_score:.1f}/100"
          f"  (raw: {sr.raw_score:.4f})")


def print_full_result(sr, agent):
    print(f"\n  {'─'*66}")
    tag = "  ⭐ BEST MATCH FOR THIS AGENT" if sr.rank == 1 and sr.available else ""
    availability_tag = "" if sr.available else "  🚫 UNAVAILABLE"
    print(f"  #{sr.rank}  {sr.mode_label}{tag}{availability_tag}")
    print(f"       Score    : {sr.utility_score:.1f}/100")
    if sr.poi_boost != 0.0:
        print(f"       POI boost: {sr.poi_boost:+.3f} added to raw score")
    print(f"       Time     : {fmt_dur(sr.route.total_duration_s)}")
    print(f"       Distance : {fmt_dist(sr.route.total_distance_m)}")
    if sr.route.transfers > 0:
        print(f"       Transfers: {sr.route.transfers}")
    if not sr.available:
        print(f"       ⚠️  Agent cannot use this mode (missing: ", end="")
        if "bike" in sr.mode_key and not agent.beliefs.get("owns_bike"):
            print("bike", end="")
        if "car" in sr.mode_key and not agent.beliefs.get("owns_car"):
            print("car", end="")
        if "pt" in sr.mode_key and not agent.beliefs.get("has_pt_access"):
            print("PT access", end="")
        print(")")
    
    # Show matched POIs
    if sr.matched_pois:
        print(f"\n  📍 Passes through {len(sr.matched_pois)} POI(s):")
        for poi in sr.matched_pois:
            boost_emoji = "✅" if poi["boost"] > 0 else "❌" if poi["boost"] < 0 else "➖"
            print(f"       {boost_emoji} {poi['name']} ({poi['type']}): {poi['boost']:+.3f} boost, {poi['distance_m']:.0f}m from route")
    
    top_match    = sr.top_matching_values
    top_conflict = sr.top_conflicting_values
    if top_match:
        print(f"       ✅ Best serves : {', '.join(d.dimension for d in top_match)}")
    if top_conflict:
        print(f"       ❌ Conflicts   : {', '.join(d.dimension for d in top_conflict)}")
    print_route_steps(sr)
    print_value_breakdown(sr, agent)


def main():
    args = parse_args()

    print("\n" + "="*66)
    print("  🧠  VALUE-BASED PERSONALISED ROUTING ENGINE")
    print("="*66)

    # Agent
    if args.agent_file:
        agent = load_agent(args.agent_file)
    elif os.path.exists("agent.json"):
        print("\n  Found agent.json — loading.")
        agent = load_agent("agent.json")
    else:
        print("\n  No agent.json found. Enter profile manually.")
        print("  Tip: create agent.json — see example_agent.json for format.")
        agent = prompt_agent()

    print_agent_summary(agent)

    # Coordinates
    if args.origin:
        from_lat, from_lon = [float(x.strip()) for x in args.origin.split(",")]
    else:
        print("\n📍 Start point:")
        from_lat, from_lon = prompt_latlon("Origin")

    if args.dest:
        to_lat, to_lon = [float(x.strip()) for x in args.dest.split(",")]
    else:
        print("\n🏁 End point:")
        to_lat, to_lon = prompt_latlon("Destination")

    if args.departure:
        departure = args.departure
    else:
        print("\n  PT departure (Enter = now — check dates with: python check_gtfs.py)")
        departure = input("  Departure: ").strip() or None

    # Straight-line distance
    dlat = math.radians(to_lat - from_lat)
    dlon = math.radians(to_lon - from_lon)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(from_lat)) * math.cos(math.radians(to_lat)) * math.sin(dlon/2)**2
    dist_km = 6371 * 2 * math.asin(math.sqrt(a))

    print(f"\n  From      : {from_lat}, {from_lon}")
    print(f"  To        : {to_lat}, {to_lon}")
    print(f"  Distance  : ~{dist_km:.1f} km")
    print(f"  Departure : {departure or 'now'}")
    print(f"\n  Computing personalised routes...\n")

    client = GraphHopperClient(base_url=args.host)
    if not client.is_alive():
        print(f"⚠️  GraphHopper not reachable at {args.host} — start the server first\n")

    # Load POIs if provided
    pois = []
    if args.pois_file:
        try:
            with open(args.pois_file, 'r') as f:
                pois = json.load(f)
            print(f"\n  📍 Loaded {len(pois)} POIs from {args.pois_file}")
            print(f"  POI proximity threshold: {args.poi_proximity}m")
        except Exception as e:
            print(f"\n  ⚠️  Failed to load POIs from {args.pois_file}: {e}")

    router  = PersonalisedRouter(client, pois=pois, poi_proximity_m=args.poi_proximity)
    results = router.route(agent, from_lat, from_lon, to_lat, to_lon,
                           departure=departure, max_walk_m=args.max_walk)

    if not results:
        print("  ❌ No routes found.")
        sys.exit(1)

    print_summary_table(results)

    best = results[0]
    top  = best.top_matching_values
    print(f"\n  ⭐ RECOMMENDED:  {best.mode_label}  (score {best.utility_score:.1f}/100)")
    if top:
        print(f"     Because it best serves: {', '.join(d.dimension for d in top)}")

    print(f"\n{'='*66}")
    print("  📋  FULL DETAILS + VALUE BREAKDOWN PER ROUTE")
    print(f"{'='*66}")

    for sr in results:
        print_full_result(sr, agent)

    print(f"\n{'='*66}\n")


if __name__ == "__main__":
    main()