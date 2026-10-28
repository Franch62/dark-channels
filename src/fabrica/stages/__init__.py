from fabrica.stages.metadata import MetadataStage
from fabrica.stages.render import RenderStage
from fabrica.stages.script import ScriptStage
from fabrica.stages.thumbnail import ThumbnailStage
from fabrica.stages.upload import UploadStage

# ordem de leitura; a execução segue depends_on (vídeo, metadados e thumbnail rodam em paralelo)
ALL_STAGES = [ScriptStage(), RenderStage(), MetadataStage(), ThumbnailStage(), UploadStage()]
STAGE_NAMES = [s.name for s in ALL_STAGES]
