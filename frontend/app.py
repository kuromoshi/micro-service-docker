from flask import Flask, render_template, request, redirect, url_for, jsonify
import requests
import os

app = Flask(__name__)

BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:5001')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/users', methods=['GET'])
def get_users():
    try:
        response = requests.get(f"{BACKEND_URL}/users")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        response = requests.get(f"{BACKEND_URL}/users/{user_id}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users', methods=['POST'])
def create_user():
    try:
        files = {'photo': (request.files['photo'].filename, request.files['photo'].read(), request.files['photo'].content_type)}
        data = {'name': request.form['name'], 'email': request.form['email']}
        response = requests.post(f"{BACKEND_URL}/users", data=data, files=files)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/<user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        files = None
        data = {'name': request.form['name'], 'email': request.form['email']}

        if 'photo' in request.files and request.files['photo'].filename:
            files = {'photo': (request.files['photo'].filename, request.files['photo'].read(), request.files['photo'].content_type)}

        response = requests.put(f"{BACKEND_URL}/users/{user_id}", data=data, files=files)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        response = requests.delete(f"{BACKEND_URL}/users/{user_id}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
