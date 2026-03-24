"""
Pagination Utilities
Helper functions for paginating API responses
"""

from typing import List, Any, TypeVar, Generic
from pydantic import BaseModel
from math import ceil

T = TypeVar('T')

class PaginationParams(BaseModel):
    """Pagination query parameters"""
    page: int = 1
    page_size: int = 50
    
    def get_skip(self) -> int:
        """Calculate number of items to skip"""
        return (self.page - 1) * self.page_size
    
    def get_limit(self) -> int:
        """Get limit (page size)"""
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response model"""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
    
    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int):
        """Create paginated response"""
        total_pages = ceil(total / page_size) if page_size > 0 else 0
        
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1
        )


def paginate(items: List[Any], page: int = 1, page_size: int = 50) -> dict:
    """
    Paginate a list of items
    
    Args:
        items: List of items to paginate
        page: Current page number (1-indexed)
        page_size: Number of items per page
    
    Returns:
        Dictionary with paginated data and metadata
    """
    total = len(items)
    total_pages = ceil(total / page_size) if page_size > 0 else 0
    
    # Calculate slice indices
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    # Get page items
    page_items = items[start_idx:end_idx]
    
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrev": page > 1
    }


async def paginate_mongo_query(collection, query: dict, pagination: PaginationParams, sort: dict = None, projection: dict = None) -> dict:
    """
    Paginate MongoDB query results (Async/Motor)
    
    Args:
        collection: MongoDB collection (Motor)
        query: Query filter
        pagination: Pagination parameters object
        sort: Sort specification
        projection: Projection specification
    
    Returns:
        Dictionary with paginated data and metadata
    """
    # Count total matching documents
    # Handle both Motor (async) and standard PyMongo (sync) if needed, 
    # but strictly this is for Motor based on app usage.
    if hasattr(collection, 'count_documents'):
        # Check if it's likely a coroutine (Motor)
        import inspect
        if inspect.iscoroutinefunction(collection.count_documents):
            total = await collection.count_documents(query)
        else:
            # Fallback (though in this codebase it seems to be wrapped/async)
            # The TenantIsolatedCollection wrapper defines count_documents as async.
            total = await collection.count_documents(query)
    else:
        total = 0

    page_size = pagination.page_size
    page = pagination.page
    total_pages = ceil(total / page_size) if page_size > 0 else 0
    
    # Calculate skip
    skip = (page - 1) * page_size
    
    # Build query
    cursor = collection.find(query, projection)
    cursor = cursor.skip(skip).limit(page_size)
    
    # Apply sorting if specified
    if sort:
        cursor = cursor.sort(list(sort.items()))
    
    # Execute query - Motor cursor.to_list requires length
    items = await cursor.to_list(length=page_size)
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrev": page > 1
    }
