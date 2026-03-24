
from authentication_service import create_access_token
from datetime import timedelta

token = create_access_token({'sub':'admin@exafluence.com', 'role':'Tenant Admin', 'tenant_id':'tenant_82dda0f33bc4'}, timedelta(days=365))
with open("new_token.txt", "w") as f:
    f.write(token)
print("Token written to new_token.txt")
