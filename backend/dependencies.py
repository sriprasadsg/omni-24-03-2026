from typing import Annotated, Any

from bson import ObjectId
from pydantic import BeforeValidator

# Custom type for PyMongo's ObjectId
# From: https://www.mongodb.com/developer/languages/python/python-quickstart-fastapi/
def validate_object_id(v: Any) -> ObjectId:
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str) and ObjectId.is_valid(v):
        return ObjectId(v)
    raise ValueError("Invalid ObjectId")

PyObjectId = Annotated[ObjectId, BeforeValidator(validate_object_id)]
