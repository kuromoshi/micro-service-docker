from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from minio import Minio
from minio.error import S3Error
import os
import uuid
from datetime import datetime
import logging
import time

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# Configuration
class Config:
    DB_HOST = os.getenv('DB_HOST', 'postgres')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'userdb')
    DB_USER = os.getenv('DB_USER', 'admin')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'admin123')
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio:9000')
    MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
    MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
    MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'profil-mahasiswa')
    MINIO_SECURE = False
    MAX_FILE_SIZE = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

config = Config()

# Database connection
def get_db_connection():
    retries = 5
    while retries > 0:
        try:
            conn = psycopg2.connect(
                host=config.DB_HOST,
                port=config.DB_PORT,
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
                cursor_factory=RealDictCursor
            )
            return conn
        except Exception as e:
            logging.error(f"Database connection failed: {e}")
            retries -= 1
            time.sleep(5)
    raise Exception("Could not connect to database")

# MinIO client
def get_minio_client():
    return Minio(
        config.MINIO_ENDPOINT,
        access_key=config.MINIO_ACCESS_KEY,
        secret_key=config.MINIO_SECRET_KEY,
        secure=config.MINIO_SECURE
    )

# Initialize database
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                photo_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        logging.info("Database initialized")
        return True
    except Exception as e:
        logging.error(f"Database init failed: {e}")
        return False

# Initialize MinIO
def init_minio():
    try:
        client = get_minio_client()
        if not client.bucket_exists(config.MINIO_BUCKET):
            client.make_bucket(config.MINIO_BUCKET)
            logging.info(f"Bucket {config.MINIO_BUCKET} created")
        return True
    except Exception as e:
        logging.error(f"MinIO init failed: {e}")
        return False

# File validation
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS

# ==================== ROUTES ====================

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200

# CREATE USER
@app.route('/users', methods=['POST'])
def create_user():
    try:
        if 'photo' not in request.files:
            return jsonify({"error": "No photo uploaded"}), 400

        file = request.files['photo']
        name = request.form.get('name')
        email = request.form.get('email')

        if not name or not email:
            return jsonify({"error": "Name and email required"}), 400

        if len(name) > 100:
            return jsonify({"error": "Name too long"}), 400

        if '@' not in email:
            return jsonify({"error": "Invalid email"}), 400

        # Cek email sudah ada
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"error": "Email already exists"}), 400

        if file.filename == '':
            cur.close()
            conn.close()
            return jsonify({"error": "No file selected"}), 400

        if not allowed_file(file.filename):
            cur.close()
            conn.close()
            return jsonify({"error": "File type not allowed"}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > config.MAX_FILE_SIZE:
            cur.close()
            conn.close()
            return jsonify({"error": "File too large (max 5MB)"}), 400

        user_id = str(uuid.uuid4())

        # Upload ke MinIO
        client = get_minio_client()
        file_ext = file.filename.rsplit('.', 1)[1].lower()
        object_name = f"{user_id}/{uuid.uuid4()}.{file_ext}"

        file.seek(0)
        client.put_object(
            config.MINIO_BUCKET,
            object_name,
            file,
            file_size,
            content_type=file.content_type
        )

        photo_url = f"http://localhost:9000/{config.MINIO_BUCKET}/{object_name}"

        cur.execute(
            "INSERT INTO users (id, name, email, photo_url) VALUES (%s, %s, %s, %s)",
            (user_id, name, email, photo_url)
        )
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "id": user_id,
            "name": name,
            "email": email,
            "photo_url": photo_url,
            "created_at": datetime.now().isoformat()
        }), 201

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# GET ALL USERS
@app.route('/users', methods=['GET'])
def get_users():
    try:
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=10, type=int)

        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 10

        offset = (page - 1) * limit

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) as count FROM users")
        total = cur.fetchone()['count']

        cur.execute("""
            SELECT id, name, email, photo_url, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        users = cur.fetchall()
        cur.close()
        conn.close()

        for user in users:
            if user['photo_url']:
                user['photo_url'] = user['photo_url'].replace('minio:9000', 'localhost:9000')

        return jsonify({
            "data": users,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit if total > 0 else 0
            }
        }), 200
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# GET USER BY ID
@app.route('/users/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, photo_url, created_at FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            if user['photo_url']:
                user['photo_url'] = user['photo_url'].replace('minio:9000', 'localhost:9000')
            return jsonify(user), 200
        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# GET USER PHOTO
@app.route('/users/<user_id>/photo', methods=['GET'])
def get_user_photo(user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT photo_url FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user or not user['photo_url']:
            return jsonify({"error": "Photo not found"}), 404

        object_name = user['photo_url'].split(f"{config.MINIO_BUCKET}/")[-1]
        client = get_minio_client()

        try:
            data = client.get_object(config.MINIO_BUCKET, object_name)
            return data.read(), 200, {'Content-Type': 'image/jpeg'}
        except Exception as e:
            return jsonify({"error": "Photo not found"}), 404

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# SEARCH USERS
@app.route('/users/search', methods=['GET'])
def search_users():
    try:
        query = request.args.get('q', '')
        if not query or len(query) < 2:
            return jsonify({"error": "Query too short"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, email, photo_url, created_at
            FROM users
            WHERE name ILIKE %s OR email ILIKE %s
            ORDER BY created_at DESC
            LIMIT 50
        """, (f'%{query}%', f'%{query}%'))

        users = cur.fetchall()
        cur.close()
        conn.close()

        for user in users:
            if user['photo_url']:
                user['photo_url'] = user['photo_url'].replace('minio:9000', 'localhost:9000')

        return jsonify({
            "query": query,
            "total": len(users),
            "data": users
        }), 200
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# UPDATE USER
@app.route('/users/<user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        name = request.form.get('name')
        email = request.form.get('email')

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

        if not user:
            cur.close()
            conn.close()
            return jsonify({"error": "User not found"}), 404

        if name and len(name) > 100:
            cur.close()
            conn.close()
            return jsonify({"error": "Name too long"}), 400

        if email:
            if '@' not in email:
                cur.close()
                conn.close()
                return jsonify({"error": "Invalid email"}), 400

            cur.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email, user_id))
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({"error": "Email already used"}), 400

        update_fields = []
        values = []

        if name:
            update_fields.append("name = %s")
            values.append(name)

        if email:
            update_fields.append("email = %s")
            values.append(email)

        if 'photo' in request.files:
            file = request.files['photo']

            if file.filename != '':
                if not allowed_file(file.filename):
                    return jsonify({"error": "File type not allowed"}), 400

                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)

                if file_size > config.MAX_FILE_SIZE:
                    return jsonify({"error": "File too large"}), 400

                if user['photo_url']:
                    try:
                        client = get_minio_client()
                        old_object = user['photo_url'].split(f"{config.MINIO_BUCKET}/")[-1]
                        client.remove_object(config.MINIO_BUCKET, old_object)
                    except Exception as e:
                        logging.error(f"Error deleting old photo: {e}")

                client = get_minio_client()
                file_ext = file.filename.rsplit('.', 1)[1].lower()
                object_name = f"{user_id}/{uuid.uuid4()}.{file_ext}"

                file.seek(0)
                client.put_object(
                    config.MINIO_BUCKET,
                    object_name,
                    file,
                    file_size,
                    content_type=file.content_type
                )

                new_photo_url = f"http://localhost:9000/{config.MINIO_BUCKET}/{object_name}"
                update_fields.append("photo_url = %s")
                values.append(new_photo_url)

        if update_fields:
            values.append(datetime.now())
            values.append(user_id)
            query = f"UPDATE users SET {', '.join(update_fields)}, updated_at = %s WHERE id = %s"
            cur.execute(query, values)
            conn.commit()

        cur.execute("SELECT id, name, email, photo_url, created_at FROM users WHERE id = %s", (user_id,))
        updated_user = cur.fetchone()
        cur.close()
        conn.close()

        if updated_user and updated_user['photo_url']:
            updated_user['photo_url'] = updated_user['photo_url'].replace('minio:9000', 'localhost:9000')

        return jsonify(updated_user), 200

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# DELETE USER
@app.route('/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT photo_url FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

        if not user:
            cur.close()
            conn.close()
            return jsonify({"error": "User not found"}), 404

        if user['photo_url']:
            try:
                client = get_minio_client()
                object_name = user['photo_url'].split(f"{config.MINIO_BUCKET}/")[-1]
                client.remove_object(config.MINIO_BUCKET, object_name)
            except Exception as e:
                logging.error(f"Error deleting photo: {e}")

        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "User deleted", "id": user_id}), 200

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# STATISTICS
@app.route('/stats', methods=['GET'])
def get_stats():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) as count FROM users")
        total_users = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) as count FROM users WHERE created_at > NOW() - INTERVAL '24 hours'")
        recent_users = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) as count FROM users WHERE photo_url IS NOT NULL")
        users_with_photos = cur.fetchone()['count']

        cur.close()
        conn.close()

        return jsonify({
            "total_users": total_users,
            "recent_users_24h": recent_users,
            "users_with_photos": users_with_photos,
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found", "timestamp": datetime.now().isoformat()}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error", "timestamp": datetime.now().isoformat()}), 500

# ==================== MAIN ====================
if __name__ == '__main__':
    logging.info("Starting API service...")
    time.sleep(10)

    for i in range(3):
        if init_db():
            break
        time.sleep(5)

    for i in range(3):
        if init_minio():
            break
        time.sleep(5)

    logging.info("✅ API ready on port 8080")
    app.run(host='0.0.0.0', port=8080, debug=True, threaded=True)
