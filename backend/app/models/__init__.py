# Import all models so SQLAlchemy registers them with Base.metadata before create_all
from app.models.user import User  # noqa: F401
from app.models.extraction import ExtractionJob, Document  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.pipeline import OAuthConnection, Pipeline, PipelineRun  # noqa: F401
from app.models.ingest import IngestAddress, IngestDocument, MobileUploadSession  # noqa: F401
