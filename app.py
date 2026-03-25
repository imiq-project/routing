"""
Flask API server for Value-Based Routing Engine
Connects the web interface to the Python routing engine
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agent import Agent
from graphhopper_client import GraphHopperClient
from personalised_router import PersonalisedRouter
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for local development

# Initialize GraphHopper client
gh_client = GraphHopperClient(base_url="http://localhost:8080")

# Load POIs
def load_pois():
    try:
        with open('example_pois.json', 'r') as f:
            return json.load(f)
    except:
        return []

# Load agent profiles
def load_agent(agent_type):
    """Load agent profile from JSON file"""
    agent_files = {
        'biospheric': 'agents/agent_biospheric.json',
        'altruistic': 'agents/agent_altruistic.json',
        'egoistic': 'agents/agent_egoistic.json',
        'hedonic': 'agents/agent_hedonic.json'
    }
    
    with open(agent_files[agent_type], 'r') as f:
        agent_data = json.load(f)
    
    return Agent.from_dict(agent_data)

@app.route('/')
def index():
    """Serve the main interface"""
    return send_file('interface.html')

@app.route('/api/route', methods=['POST'])
def calculate_route():
    """
    Calculate value-based routes
    
    Request JSON:
    {
        "origin": [lat, lon],
        "destination": [lat, lon],
        "agent": "biospheric|altruistic|egoistic|hedonic",
        "pois": true|false
    }
    
    Response JSON:
    [
        {
            "rank": 1,
            "mode": "bike",
            "mode_label": "🚴 Bike",
            "score": 94.2,
            "time_min": 28,
            "distance_km": 8.0,
            "available": true,
            "poi_boost": 1.2,
            "matched_pois": [...],
            "legs": [...]  # Detailed leg-by-leg geometry
        },
        ...
    ]
    """
    try:
        data = request.json
        
        # Extract parameters
        origin = data['origin']  # [lat, lon]
        destination = data['destination']
        agent_type = data.get('agent', 'biospheric')
        pois_enabled = data.get('pois', True)
        
        # Load agent
        agent = load_agent(agent_type)
        
        # Load POIs if enabled, Empty for now, but can be extended to load from fiware
        pois = load_pois() if pois_enabled else []
        
        # Initialize router
        router = PersonalisedRouter(
            gh_client, 
            pois=pois if pois_enabled else None,
            poi_proximity_m=100
        )
        
        # Calculate routes
        # IMPORTANT: Use a departure time within GTFS calendar range
        # Your GTFS is valid: 2025-10-10 to 2026-10-09
        # Using a fixed date within this range for reliability
        from datetime import datetime, timezone
        departure = datetime(2025, 11, 15, 9, 0, tzinfo=timezone.utc)
        
        results = router.route(
            agent=agent,
            from_lat=origin[0],
            from_lon=origin[1],
            to_lat=destination[0],
            to_lon=destination[1],
            departure=departure.isoformat(),  # Pass as ISO string
            max_walk_m=500
        )
        
        # Format response
        routes = []
        for result in results:
            # Extract leg-by-leg information for visualization
            legs_data = []
            for leg in result.route.legs:
                leg_info = {
                    'mode': leg.mode,
                    'description': leg.description,
                    'distance_m': leg.distance_m,
                    'duration_s': leg.duration_s,
                    'from_name': getattr(leg, 'from_name', None),
                    'to_name': getattr(leg, 'to_name', None)
                }
                
                # Add PT-specific information if this is a PT leg
                if hasattr(leg, 'route_id'):
                    leg_info['route_id'] = leg.route_id
                    leg_info['trip_headsign'] = getattr(leg, 'trip_headsign', '')
                    leg_info['departure_time'] = getattr(leg, 'departure_time', None)
                    leg_info['arrival_time'] = getattr(leg, 'arrival_time', None)
                    leg_info['from_stop'] = getattr(leg, 'from_stop', '')
                    leg_info['to_stop'] = getattr(leg, 'to_stop', '')
                    leg_info['num_stops'] = getattr(leg, 'num_stops', 0)
                    
                    # Add stop information for PT legs
                    if hasattr(leg, 'stops') and leg.stops:
                        leg_info['stops'] = leg.stops
                
                legs_data.append(leg_info)
            
            routes.append({
                'rank': result.rank,
                'mode': result.mode_key,
                'mode_label': result.mode_label,
                'score': round(result.utility_score, 1),
                'time_min': result.route.duration_min,
                'distance_km': result.route.distance_km,
                'available': result.available,
                'poi_boost': round(result.poi_boost, 2),
                'matched_pois': result.matched_pois,
                'geometry': result.route.geometry,  # Overall route geometry
                'legs': legs_data  # Detailed leg information
            })
        
        return jsonify(routes)
    
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'type': type(e).__name__,
            'traceback': traceback.format_exc()
        }), 500

@app.route('/api/agents', methods=['GET'])
def get_agents():
    """Get available agent profiles with their values"""
    agents = {}
    
    for agent_type in ['biospheric', 'altruistic', 'egoistic', 'hedonic']:
        agent = load_agent(agent_type)
        
        # Get top values
        top_values = sorted(
            agent.value_weights.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:5]
        
        agents[agent_type] = {
            'id': agent.id,
            'top_values': {k: round(v, 2) for k, v in top_values},
            'beliefs': agent.beliefs
        }
    
    return jsonify(agents)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Check if GraphHopper server is running"""
    try:
        is_alive = gh_client.is_alive()
        return jsonify({
            'status': 'ok' if is_alive else 'error',
            'graphhopper': 'running' if is_alive else 'not running',
            'message': 'All systems operational' if is_alive else 'GraphHopper server not responding'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🗺️  Value-Based Routing Engine - Web Interface")
    print("="*60)
    print("\n📍 Starting server...")
    print(f"   Interface: http://localhost:5000")
    print(f"   API: http://localhost:5000/api/route")
    print("\n⚠️  Make sure GraphHopper is running on http://localhost:8080")
    print("="*60 + "\n")
    
    # Check GraphHopper connection
    try:
        if gh_client.is_alive():
            print("✅ GraphHopper server connected\n")
        else:
            print("❌ WARNING: GraphHopper server not responding")
            print("   Start it with: java -Xmx4g -jar graphhopper/graphhopper-web-10.0.jar server graphhopper/config.yml\n")
    except:
        print("❌ WARNING: Could not connect to GraphHopper")
        print("   Start it with: java -Xmx4g -jar graphhopper/graphhopper-web-10.0.jar server graphhopper/config.yml\n")
    
    app.run(debug=True, port=5000, host='0.0.0.0')