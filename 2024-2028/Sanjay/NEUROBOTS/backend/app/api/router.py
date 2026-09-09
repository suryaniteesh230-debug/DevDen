from fastapi import APIRouter, Depends

from app.api.routes import auth, assessments, encounters, multimodal, patients, queue, speech
from app.core.security import require_staff_user


api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)

clinical_router = APIRouter(dependencies=[Depends(require_staff_user)])
clinical_router.include_router(patients.router)
clinical_router.include_router(encounters.router)
clinical_router.include_router(queue.router)
clinical_router.include_router(multimodal.router)
clinical_router.include_router(speech.router)
clinical_router.include_router(assessments.router)
api_router.include_router(clinical_router)
