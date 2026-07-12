from fastapi import APIRouter

# Bridge management routes have moved to /v1/admin/bridge/... (admin-only).
# SMS notify has moved to /v1/hip/sms-notify (customer-facing).
router = APIRouter()
