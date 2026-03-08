from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import logging

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

API_URL = os.getenv('API_URL', 'http://localhost:8080')

@app.route('/users', methods=['GET'])
def get_users():
    try:
        response = requests.get(f"{API_URL}/users")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/users/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        response = requests.get(f"{API_URL}/users/{user_id}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/users', methods=['POST'])
def create_user():
    try:
        files = {}
        if 'photo' in request.files:
            photo = request.files['photo']
            files = {'photo': (photo.filename, photo.read(), photo.content_type)}

        data = {
            'name': request.form.get('name'),
            'email': request.form.get('email')
        }

        response = requests.post(f"{API_URL}/users", data=data, files=files)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/users/<user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        files = {}
        if 'photo' in request.files and request.files['photo'].filename:
            photo = request.files['photo']
            files = {'photo': (photo.filename, photo.read(), photo.content_type)}

        data = {}
        if request.form.get('name'):
            data['name'] = request.form.get('name')
        if request.form.get('email'):
            data['email'] = request.form.get('email')

        response = requests.put(f"{API_URL}/users/{user_id}", data=data, files=files if files else None)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        response = requests.delete(f"{API_URL}/users/{user_id}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
