# API Module - This should trigger violations
# AI GENERATED/UPDATED CODE - Added by Claude Code
# Second update by Claude Code to test detection
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/users', methods=['GET'])
def get_users():
    """Get all users from database"""
    users = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 3, "name": "Charlie"}
    ]
    return jsonify(users)

print("Hello there")
print("Thjis is an experiment for testing")

# ==================== THIRD BATCH - DEMO VIDEO ====================
@app.route('/users/stats', methods=['GET'])
def get_stats():
    """Get user statistics - AI Generated for demo"""
    users = [
        {"id": 1, "name": "Alice", "active": True},
        {"id": 2, "name": "Bob", "active": False},
        {"id": 3, "name": "Charlie", "active": True}
    ]
    total = len(users)
    active = sum(1 for u in users if u["active"])
    return jsonify({
        "total_users": total,
        "active_users": active,
        "inactive_users": total - active
    })
# ==================== END THIRD BATCH ====================

@app.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get a single user by ID - AI Generated"""
    users = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 3, "name": "Charlie"}
    ]
    user = next((u for u in users if u["id"] == user_id), None)
    if user:
        return jsonify(user)
    return jsonify({"error": "User not found"}), 404

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint - AI Generated"""
    return jsonify({"status": "healthy", "version": "1.0.0"})

@app.route('/users', methods=['POST'])
def create_user():
    """Create a new user - AI Generated endpoint"""
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "Name is required"}), 400
    new_user = {
        "id": 4,
        "name": data['name']
    }
    return jsonify(new_user), 201

@app.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user by ID - AI Generated endpoint"""
    return jsonify({"message": f"User {user_id} deleted"}), 200

# ==================== NEW CODE ADDED BY CLAUDE CODE ====================
# Testing diff logging in on_moved handler
@app.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """Update user information - AI Generated endpoint"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    updated_user = {
        "id": user_id,
        "name": data.get('name', 'Unknown'),
        "email": data.get('email', ''),
        "updated": True
    }
    return jsonify(updated_user), 200
# ==================== END NEW CODE ====================

# ==================== FOURTH BATCH - SOURCE TRACKING TEST ====================
@app.route('/users/bulk', methods=['POST'])
def bulk_create_users():
    """Bulk create multiple users - AI Generated for source tracking test"""
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"error": "Users array is required"}), 400

    created_users = []
    for i, user_data in enumerate(data['users']):
        new_user = {
            "id": 100 + i,
            "name": user_data.get('name', f'User_{i}'),
            "email": user_data.get('email', ''),
            "created_by": "bulk_api"
        }
        created_users.append(new_user)

    return jsonify({
        "created": len(created_users),
        "users": created_users
    }), 201
# ==================== END FOURTH BATCH ====================

# ==================== SECOND BATCH - TESTING DIFF LOGGING ====================
@app.route('/users/search', methods=['GET'])
def search_users():
    """Search users by name - AI Generated endpoint for testing diff logging"""
    query = request.args.get('q', '')
    users = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 3, "name": "Charlie"}
    ]
    results = [u for u in users if query.lower() in u["name"].lower()]
    return jsonify({"query": query, "results": results, "count": len(results)})
# ==================== END SECOND BATCH ====================

if __name__ == '__main__':
    app.run(debug=True)
