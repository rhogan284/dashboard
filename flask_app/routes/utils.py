from flask import jsonify


def json_error(message: str, code: int, **extra):
    return jsonify({'error': message, **extra}), code
