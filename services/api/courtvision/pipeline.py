from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence

from .repository import Repository
from .state_machine import AnalysisStage


@dataclass(frozen=True, slots=True)
class PipelineContext:
    job_id: str
    source_path: str
    repository: Repository


class PipelineStage(ABC):
    target_stage: AnalysisStage

    @abstractmethod
    def run(self, context: PipelineContext) -> dict[str, Any]:
        raise NotImplementedError


class AnalysisPipeline:
    def __init__(
        self,
        repository: Repository,
        stages: Sequence[PipelineStage],
    ):
        self.repository = repository
        self.stages = list(stages)

    def _start_index(self, job: dict[str, Any]) -> tuple[int, bool]:
        current = AnalysisStage(job["stage"])
        if current is AnalysisStage.FAILED:
            resume_stage = AnalysisStage(job["checkpoint"]["resume_stage"])
            for index, stage in enumerate(self.stages):
                if stage.target_stage is resume_stage:
                    return index, True
            raise ValueError(f"resume stage {resume_stage.value} is unavailable")
        for index, stage in enumerate(self.stages):
            if stage.target_stage is current:
                if job["checkpoint"].get("active_stage") == current.value:
                    return index, True
                return index + 1, False
        return 0, False

    def run(self, job_id: str) -> dict[str, Any]:
        job = self.repository.get_job(job_id)
        start_index, retrying = self._start_index(job)
        context = PipelineContext(
            job_id=job_id,
            source_path=job["source_path"],
            repository=self.repository,
        )
        if retrying:
            job = self.repository.update_job_stage(
                job_id,
                AnalysisStage.RETRYING,
                progress=job["progress"],
                checkpoint=job["checkpoint"],
            )

        total = max(len(self.stages), 1)
        for index in range(start_index, len(self.stages)):
            stage = self.stages[index]
            checkpoint = {"active_stage": stage.target_stage.value}
            try:
                self.repository.update_job_stage(
                    job_id,
                    stage.target_stage,
                    progress=index / total,
                    checkpoint=checkpoint,
                )
                result = stage.run(context)
                self.repository.save_result(
                    job_id=job_id,
                    kind=stage.target_stage.value,
                    payload=result,
                )
                self.repository.update_job_progress(
                    job_id,
                    progress=(index + 1) / total,
                    checkpoint={"completed_stage": stage.target_stage.value},
                )
            except Exception as error:
                self.repository.update_job_stage(
                    job_id,
                    AnalysisStage.FAILED,
                    progress=index / total,
                    checkpoint={"resume_stage": stage.target_stage.value},
                    error_message=str(error),
                )
                raise
        return self.repository.get_job(job_id)
