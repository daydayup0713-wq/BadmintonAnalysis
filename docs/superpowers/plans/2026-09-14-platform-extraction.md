# BadmintonAnalysis Platform Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce and publish a runnable badminton analysis platform whose current tree contains no bundled detection model implementation, model weights, training dataset, or model-generated results while retaining the source repository's complete Git history.

**Architecture:** FastAPI and SQLite accept provider-neutral analysis JSON, persist it in the existing result kinds, calculate platform-owned metrics and expose the existing summary/export/review APIs. Next.js and Taro present uploaded jobs, external-result import, synthetic demo data, analysis, review and export without attempting to launch a local GPU worker.

**Tech Stack:** Python 3.10-3.12, FastAPI, Pydantic 2, SQLite, ReportLab, FFmpeg, Next.js 15, React 18, Taro 4, TypeScript, PowerShell, Git.

**Spec:** `docs/superpowers/specs/2026-09-14-platform-extraction-design.md`

## Global Constraints

- Retain the full existing SoloShuttlePose Git history; do not rewrite history and do not claim old commits are model-free.
- Remove model implementations, four local weights, ShuttleSet, training utilities and model-generated data from the final working tree.
- Keep the platform runnable without CUDA, PyTorch, TorchVision or an NVIDIA GPU.
- Preserve low-confidence and missing-evidence behavior; never fabricate pose, trajectory, hit or shot data.
- Every external import records non-empty `provider` and `provider_version` values and uses `external` as the raw data origin.
- Synthetic demo data must be deterministic and manually constructed, with no copied match video, dataset row or historical model result.
- The final target is `https://github.com/daydayup0713-wq/BadmintonAnalysis`, with the target's existing README commit merged rather than force-pushed away.

---

### Task 1: Add the provider-neutral waiting state and import contract

**Files:**
- Create: `services/api/courtvision/importing.py`
- Modify: `services/api/courtvision/state_machine.py`
- Modify: `services/api/courtvision/contracts.py`
- Test: `tests/test_importing.py`
- Test: `tests/test_state_machine.py`

**Interfaces:**
- Consumes: `Repository.save_result()`, `Repository.update_job_stage()`, existing `PlayerPoseFrame` and `DataOrigin` contracts.
- Produces: `AnalysisStage.AWAITING_RESULTS`; Pydantic `ExternalAnalysisImport`; `import_external_results(repository: Repository, job_id: str, payload: ExternalAnalysisImport) -> dict[str, Any]`.

- [ ] **Step 1: Write failing state and validation tests**

```python
def test_uploaded_job_waits_for_external_results(self):
    validate_transition(AnalysisStage.UPLOADED, AnalysisStage.AWAITING_RESULTS)
    validate_transition(AnalysisStage.AWAITING_RESULTS, AnalysisStage.METRICS)

def test_external_import_requires_provider_identity(self):
    with self.assertRaises(ValidationError):
        ExternalAnalysisImport.model_validate({
            "provider": "",
            "provider_version": "",
            "video": {"fps": 30, "width": 1280, "height": 720,
                      "total_frames": 300, "duration_seconds": 10},
            "rallies": [], "poses": [], "shuttle": [],
            "hits": [], "shots": [],
        })
```

- [ ] **Step 2: Run the focused tests and confirm the missing enum/model failures**

Run: `python -m unittest tests.test_state_machine tests.test_importing -v`

Expected: FAIL because `AWAITING_RESULTS` and `ExternalAnalysisImport` do not exist.

- [ ] **Step 3: Define the exact import models**

Implement in `importing.py`:

```python
class VideoImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fps: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    total_frames: int = Field(gt=0)
    duration_seconds: float = Field(gt=0)

class PoseImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame: int = Field(ge=0)
    timestamp_us: int = Field(ge=0)
    top_keypoints: list[list[float]] | None = None
    bottom_keypoints: list[list[float]] | None = None
    confidence: float = Field(ge=0, le=1)

class ExternalAnalysisImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=100)
    provider_version: str = Field(min_length=1, max_length=100)
    video: VideoImport
    court_points: list[list[float]] | None = None
    net_points: list[list[float]] | None = None
    rallies: list[dict[str, Any]] = Field(default_factory=list)
    poses: list[PoseImport] = Field(default_factory=list)
    shuttle: list[dict[str, Any]] = Field(default_factory=list)
    hits: list[dict[str, Any]] = Field(default_factory=list)
    shots: list[dict[str, Any]] = Field(default_factory=list)
```

Add validators that require each non-null keypoint set to contain exactly 17 finite `[x, y]` pairs, require frames to be smaller than `video.total_frames`, and require every imported confidence value to be in `[0, 1]`.

- [ ] **Step 4: Implement state transitions**

Add `AWAITING_RESULTS = "awaiting_results"` and allow only these new paths:

```python
AnalysisStage.UPLOADED -> AnalysisStage.AWAITING_RESULTS
AnalysisStage.AWAITING_RESULTS -> AnalysisStage.METRICS
```

Keep the existing review, rendering, failure, cancellation and retry transitions unchanged.

- [ ] **Step 5: Run the focused tests**

Run: `python -m unittest tests.test_state_machine tests.test_importing -v`

Expected: PASS.

- [ ] **Step 6: Commit the contract**

```powershell
git add services/api/courtvision/importing.py services/api/courtvision/state_machine.py services/api/courtvision/contracts.py tests/test_importing.py tests/test_state_machine.py
git commit -m "feat: add external analysis import contract"
```

### Task 2: Persist external results and provide a synthetic demo

**Files:**
- Create: `services/api/courtvision/fixtures/synthetic-demo.json`
- Modify: `services/api/courtvision/importing.py`
- Modify: `tests/test_importing.py`

**Interfaces:**
- Consumes: `ExternalAnalysisImport`, `build_player_movement_metrics()`, `build_swing_metrics()`, `Repository.save_result()`.
- Produces: the existing result kinds `validating`, `calibrating`, `segmenting`, `pose_tracking`, `shuttle_tracking`, `event_detection`, `metrics`, `review_required`, plus `external_import` provenance.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_import_saves_platform_result_kinds_and_requires_review(self):
    payload = synthetic_payload(provider="fixture", provider_version="1")
    result = import_external_results(self.repo, self.job["id"], payload)
    self.assertEqual(result["stage"], "review_required")
    self.assertEqual(
        self.repo.get_result(self.job["id"], "external_import"),
        {"provider": "fixture", "provider_version": "1"},
    )
    self.assertEqual(
        self.repo.get_result(self.job["id"], "pose_tracking")["frames"][0]["origin"],
        "external",
    )

def test_empty_import_marks_missing_evidence_without_inventing_events(self):
    result = import_external_results(self.repo, self.job["id"], empty_payload())
    review = self.repo.get_result(self.job["id"], "review_required")
    self.assertEqual(review["status"], "review_required")
    self.assertEqual(self.repo.get_result(self.job["id"], "event_detection")["shots"], [])
```

- [ ] **Step 2: Run and confirm failures occur because persistence is not implemented**

Run: `python -m unittest tests.test_importing -v`

Expected: FAIL on missing saved result kinds.

- [ ] **Step 3: Implement deterministic persistence and platform calculations**

In `import_external_results()`, save:

```python
repository.save_result(job_id=job_id, kind="external_import", payload={
    "provider": payload.provider,
    "provider_version": payload.provider_version,
})
repository.save_result(job_id=job_id, kind="validating", payload=payload.video.model_dump())
repository.save_result(job_id=job_id, kind="calibrating", payload={
    "court_points": payload.court_points,
    "net_points": payload.net_points,
})
repository.save_result(job_id=job_id, kind="segmenting", payload={"rallies": payload.rallies})
repository.save_result(job_id=job_id, kind="pose_tracking", payload={
    "frames": normalized_poses,
    "identities": [],
})
repository.save_result(job_id=job_id, kind="shuttle_tracking", payload={"points": payload.shuttle})
repository.save_result(job_id=job_id, kind="event_detection", payload={
    "rallies": payload.rallies,
    "hits": payload.hits,
    "shots": payload.shots,
})
```

Compute movement and swing metrics only when both valid pose frames and court points exist. Otherwise save explicit availability flags and missing-evidence reasons. Transition `awaiting_results -> metrics -> review_required`, with checkpoint `{provider, provider_version, imported: true}`.

- [ ] **Step 4: Add a manually constructed synthetic fixture**

Create a 5-second, 30-FPS fixture with one rally, two hit candidates, 17-point top/bottom skeletons on a small set of frames, a short shuttle path and normalized court points. Use `provider: "synthetic-demo"`, `provider_version: "1"`; do not copy any current `res`, `data`, `exports`, `videos` or ShuttleSet value.

- [ ] **Step 5: Run import and platform metric tests**

Run: `python -m unittest tests.test_importing tests.test_metrics tests.test_biomechanics tests.test_tactics -v`

Expected: PASS.

- [ ] **Step 6: Commit importer and fixture**

```powershell
git add services/api/courtvision/importing.py services/api/courtvision/fixtures/synthetic-demo.json tests/test_importing.py
git commit -m "feat: import provider-neutral analysis results"
```

### Task 3: Remove model execution from the API

**Files:**
- Modify: `services/api/courtvision/api.py`
- Modify: `services/api/courtvision/__init__.py`
- Modify: `tests/test_api.py`
- Delete: `services/api/courtvision/adapters.py`
- Delete: `services/api/courtvision/gpu_pipeline.py`
- Delete: `services/api/courtvision/legacy_pipeline.py`
- Delete: `services/api/courtvision/local_runtime.py`
- Delete: `services/api/courtvision/model_registry.py`
- Delete: `services/api/courtvision/runtime.py`
- Delete: `services/api/courtvision/worker.py`
- Delete: `services/api/courtvision/training/`
- Delete: model-specific tests listed in Task 5.

**Interfaces:**
- Consumes: `ExternalAnalysisImport`, `import_external_results()`, existing repository and export functions.
- Produces: `POST /api/jobs/{job_id}/results/import`, provider-neutral `/api/health`, synthetic `POST /api/demo/bootstrap`; removes `/api/models`, `/api/runtime` and executable `/api/jobs/{job_id}/run` behavior.

- [ ] **Step 1: Replace API tests with failing platform-only expectations**

```python
def test_health_identifies_analysis_platform(self):
    response = self.client.get("/api/health")
    self.assertEqual(response.json(), {
        "status": "ok",
        "service": "BadmintonAnalysis",
        "analysis_mode": "external_results",
    })

def test_upload_waits_for_external_results(self):
    response = self.client.post(
        "/api/uploads?title=Training",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
    )
    self.assertEqual(response.status_code, 201)
    self.assertEqual(response.json()["job"]["stage"], "awaiting_results")

def test_import_endpoint_returns_summary(self):
    response = self.client.post(
        f"/api/jobs/{self.job_id}/results/import",
        json=synthetic_payload_dict(),
    )
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["job"]["stage"], "review_required")
```

- [ ] **Step 2: Run the API tests and confirm old model behavior causes failures**

Run: `python -m unittest tests.test_api -v`

Expected: FAIL on health payload, upload stage and missing import endpoint.

- [ ] **Step 3: Refactor `create_app()`**

Remove `runtime_probe` and `worker_launcher` parameters and all model imports. Set the FastAPI description to `Provider-neutral badminton analysis, review and export service`. Implement:

```python
@app.post("/api/jobs/{job_id}/results/import")
def import_results(job_id: str, payload: ExternalAnalysisImport) -> dict[str, Any]:
    get_job_or_404(job_id)
    import_external_results(repo, job_id, payload)
    return build_summary(job_id)
```

After job creation or upload, transition to `AWAITING_RESULTS`. Change `/api/demo/bootstrap` to load `fixtures/synthetic-demo.json`, create a synthetic session/job and invoke the same importer. Remove model and runtime routes. Keep `/api/jobs/{job_id}/run` only as a compatibility response with HTTP 409 and detail code `external_results_required`, without starting any process.

- [ ] **Step 4: Delete model execution modules and update package documentation string**

Delete the files named above and change `courtvision.__init__` to describe the provider-neutral platform. Ensure no remaining import references any deleted module.

- [ ] **Step 5: Run API, repository, export and evaluation tests**

Run: `python -m unittest tests.test_api tests.test_repository tests.test_exporting tests.test_exporting_media tests.test_evaluation -v`

Expected: PASS.

- [ ] **Step 6: Commit the platform API**

```powershell
git add services/api/courtvision tests/test_api.py
git commit -m "refactor: remove bundled model execution"
```

### Task 4: Update Web and mini-program platform flows

**Files:**
- Modify: `apps/web/app/tasks/page.tsx`
- Modify: `apps/web/app/app-shell.tsx`
- Modify: `apps/web/app/layout.tsx`
- Modify: `apps/web/app/analysis/page.tsx`
- Delete: `apps/web/app/models/page.tsx`
- Modify: `apps/mini/project.config.json`
- Modify: `apps/mini/src/pages/index/index.tsx`
- Modify: relevant Web test files under `apps/web/app/*.test.ts`

**Interfaces:**
- Consumes: job stage `awaiting_results`, `POST /api/jobs/{job_id}/results/import`, unchanged summary structure.
- Produces: upload-only job creation, JSON result import, synthetic demo discovery, no model/GPU branding.

- [ ] **Step 1: Write failing TypeScript tests for labels and API URL construction**

Add pure helpers exported from `apps/web/app/tasks/task-actions.ts` and test:

```typescript
it("labels an uploaded external job as waiting for results", () => {
  expect(stageName("awaiting_results")).toBe("等待导入分析结果");
});

it("builds the external import endpoint", () => {
  expect(importResultsUrl("http://127.0.0.1:8000", "job-1"))
    .toBe("http://127.0.0.1:8000/api/jobs/job-1/results/import");
});
```

- [ ] **Step 2: Run the tests and confirm helpers are missing**

Run: `npm test -w @courtvision/web -- --runInBand`

Expected: FAIL because `task-actions.ts` and its exports do not exist. If the workspace has no test script, run `npx tsc --noEmit -p apps/web/tsconfig.json` after adding a temporary import and confirm the missing module error, then add a permanent Node test script using the existing test convention.

- [ ] **Step 3: Implement upload and JSON import UI**

Change the upload success status to `上传完成，等待导入外部分析结果` and do not call `/run`. Add a second form with a job selector limited to `awaiting_results` or `failed`, a `.json` file input, `JSON.parse(await file.text())`, and POST to `/api/jobs/{id}/results/import`. On success reload jobs and link to `/analysis?job=<id>`.

- [ ] **Step 4: Remove model routes and branding**

Remove the “models” navigation entry and page. Replace product text with `BadmintonAnalysis`, `外部结果分析平台`, and `结果复核与导出`; remove claims about GPU queue or local models. Preserve pose, trajectory, rally and metric visualization because they display provider-neutral contract data.

- [ ] **Step 5: Update Taro branding and task status text**

Change project description and home-page label to `BadmintonAnalysis`; display `awaiting_results` as `等待导入分析结果`; remove SoloShuttlePose and GPU claims.

- [ ] **Step 6: Build both clients**

Run: `npm run web:build`

Expected: PASS with all Web routes compiled and `/models` absent.

Run: `npm run mini:build`

Expected: PASS.

- [ ] **Step 7: Commit frontend changes**

```powershell
git add apps/web apps/mini
git commit -m "feat: add external result import workflow"
```

### Task 5: Remove bundled model assets and rewrite delivery documentation

**Files:**
- Modify: `README.md`
- Create: `NOTICE.md`
- Create: `docs/EXTERNAL_RESULTS.md`
- Create: `docs/WINDOWS_SETUP.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/API_CONTRACTS.md`
- Modify: `docs/TEST_AND_ACCEPTANCE.md`
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Modify: `scripts/windows/setup.ps1`
- Modify: `scripts/windows/check-environment.ps1`
- Modify: `scripts/windows/start.ps1`
- Delete: `requirements-windows-nvidia.txt`
- Delete: `requirements-windows-runtime.txt`
- Delete: `WINDOWS_NVIDIA_部署运行说明.md`
- Delete: `src/`, `ShuttleSet/`, `videos/`, `res/`, `data/`, `exports/`, `logs/`, `draft/`, `references/`
- Delete: `docs/ALGORITHM_AUDIT.md`
- Delete: `docs/MODEL_MANIFEST.md`
- Delete: `docs/SHUTTLESET_TRAINING.md`
- Delete: `docs/ACCEPTANCE_EVALUATION.md`
- Delete: `docs/acceptance/`
- Delete: `scripts/audit_shuttleset.py`
- Delete: `scripts/evaluate_shuttleset.py`
- Delete: `scripts/train_shuttleset.py`
- Delete: `tests/test_adapters.py`
- Delete: `tests/test_gpu_pipeline.py`
- Delete: `tests/test_legacy_pipeline.py`
- Delete: `tests/test_local_runtime.py`
- Delete: `tests/test_model_registry.py`
- Delete: `tests/test_training_cli.py`
- Delete: `tests/test_training_data.py`
- Delete: `tests/test_windows_delivery_assets.py`

**Interfaces:**
- Consumes: the external import API and synthetic demo created in Tasks 1-3.
- Produces: model-free installation instructions, provider contract documentation and explicit Git-history notice.

- [ ] **Step 1: Write failing repository-boundary tests**

Create `tests/test_repository_boundary.py`:

```python
FORBIDDEN_PATHS = [
    "src", "ShuttleSet", "services/api/courtvision/model_registry.py",
    "services/api/courtvision/gpu_pipeline.py",
]

def test_bundled_model_paths_are_absent(self):
    for relative in FORBIDDEN_PATHS:
        self.assertFalse((ROOT / relative).exists(), relative)

def test_notice_discloses_retained_history(self):
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    self.assertIn("当前工作树不包含", notice)
    self.assertIn("Git 历史", notice)
    self.assertIn("旧提交", notice)
```

- [ ] **Step 2: Run and confirm forbidden paths still cause failures**

Run: `python -m unittest tests.test_repository_boundary -v`

Expected: FAIL because model directories exist and `NOTICE.md` is missing.

- [ ] **Step 3: Rewrite platform documentation and scripts**

README must describe features, quick start, synthetic demo, external import and limits. `NOTICE.md` must explicitly say the current tree excludes bundled open-source models/weights/data/results while retained old Git commits may still contain them. `docs/EXTERNAL_RESULTS.md` must include one complete JSON request matching `ExternalAnalysisImport`. Windows setup must install only Python, Node and FFmpeg, create `.venv`, run `pip install -e .[dev]`, run `npm ci`, and start API/Web without CUDA variables.

- [ ] **Step 4: Delete model, dataset and generated-result paths**

Delete exactly the paths listed in this task. Preserve `LICENSE` because Git history and any retained upstream-derived code remain subject to their recorded notice; explain this in `NOTICE.md`. Remove PyTorch, TorchVision, OpenCV, NumPy, SciPy, Pandas and NVIDIA installation requirements unless a retained platform module directly imports them. Keep ReportLab and FFmpeg for document and video export.

- [ ] **Step 5: Run boundary and text scans**

Run: `python -m unittest tests.test_repository_boundary -v`

Expected: PASS.

Run: `rg -n -i "SoloShuttlePose|TrackNet|ShuttleSet|kpRCNN|model_registry|gpu_pipeline|courtvision\.worker|src/models/weights" --glob '!NOTICE.md' --glob '!docs/superpowers/**' --glob '!.git/**' .`

Expected: no matches. References in `NOTICE.md` and the approved design/plan are allowed because they disclose removed content and retained history.

- [ ] **Step 6: Run the full model-free test/build suite**

Run: `python -m unittest discover -s tests -v`

Expected: all remaining tests PASS.

Run: `npm ci`, then `npm run web:build`, then `npm run mini:build`.

Expected: all commands exit 0.

- [ ] **Step 7: Commit cleanup and documentation**

```powershell
git add -A
git commit -m "docs: publish model-free analysis platform"
```

Before committing, inspect `git status --short` and verify `.venv`, `node_modules`, `.next`, `dist`, SQLite files and caches are not staged.

### Task 6: Preserve both histories and publish to BadmintonAnalysis

**Files:**
- No product files created or modified.
- Git metadata: add remote `badminton-analysis`, fetch its `main`, merge its existing commit, push final `main`.

**Interfaces:**
- Consumes: verified platform branch HEAD and remote commit `5eb9d618c1282a749e487c7a9460a41db1a610a8` observed before implementation.
- Produces: `refs/heads/main` at `https://github.com/daydayup0713-wq/BadmintonAnalysis` pointing to the verified merged commit.

- [ ] **Step 1: Confirm local history and clean staging state**

Run: `git log --oneline --decorate -8`

Run: `git status --short`

Expected: intended platform commits are present; generated directories are untracked/ignored and no product changes remain unstaged.

- [ ] **Step 2: Add and fetch the target remote**

```powershell
git remote add badminton-analysis https://github.com/daydayup0713-wq/BadmintonAnalysis.git
git fetch badminton-analysis main
```

If the remote already exists, verify its URL and use `git remote set-url badminton-analysis ...` only when it differs.

- [ ] **Step 3: Merge the target repository's existing history**

Run: `git merge badminton-analysis/main --allow-unrelated-histories --no-ff -m "chore: merge BadmintonAnalysis repository history"`

Expected: only `README.md` may conflict. Resolve it by keeping the completed platform README, stage it, and continue the merge. Do not force-push.

- [ ] **Step 4: Re-run release verification after the merge**

Run: `python -m unittest discover -s tests -v`

Run: `npm run web:build`

Run: `npm run mini:build`

Run the forbidden-text scan from Task 5.

Expected: tests/builds pass and only allowed disclosure documents contain removed-model names.

- [ ] **Step 5: Push the verified commit as target `main`**

Run: `git push badminton-analysis HEAD:main`

Expected: fast-forward update of target `main`; no force flag.

- [ ] **Step 6: Verify the remote ref**

Run: `git ls-remote badminton-analysis refs/heads/main`

Run: `git rev-parse HEAD`

Expected: both hashes are identical. Report the repository URL and final commit hash to the user.
