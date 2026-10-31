"""Controlled-response Earth Engine world for the task 10-30 table producer tests: the real offline client builds every
graph; only server calls are faked (asset metadata/listing, computeFeatures, toAsset tasks, setDeadline, getInfo). A
completed task "computes" its destination table with ``server(asset_id)``, shaped like the producer's real export
(admin rows, identity properties, days_present_YYYYMM / composite_dates, {field}_{period}_mean values; masked months
are null or absent)."""

import json
import re

import numpy as np
import pandas as pd

from cloud.ipcch import climate_tables as ct
from cloud.ipcch import table_producers as tp
from cloud.ipcch.climate_ee import AssetRefs
from tests.cloud.ee_offline import offline_ee

AMBIGUOUS = "Asset '{}' does not exist or doesn't allow this operation."
MAX_POLLS = 1000          # per task: a scenario that never terminates fails fast instead of looping on the wait budget


class RunawayPoll(BaseException):
    """BaseException on purpose: EETransport._wait retries ordinary status exceptions until its budget."""
REFS = ct.TableRefs()                                             # the static (existing) chunks
FAMILIES = ct.TableRefs(year_chunks=ct.year_chunks(2040))          # resolves produced names incl. the rolling chunks
OUT_ROOT = "projects/feisty-flames-511718-d4/assets/"


def feature_page(frame, params):
    """One computeFeatures response page of ``frame`` (properties only; NaN -> null), as the server pages it."""
    assert "fileFormat" not in params, "reads must page explicitly"
    size, start = int(params["pageSize"]), int(params.get("pageToken") or 0)
    part = frame.iloc[start:start + size].astype(object).where(frame.iloc[start:start + size].notna(), None)
    out = {"type": "FeatureCollection",
           "features": [{"type": "Feature", "geometry": None, "properties": row} for row in part.to_dict("records")]}
    if start + size < len(frame):
        out["nextPageToken"] = str(start + size)
    return out


def vi_tags(sensor, year, through=None):
    tags = [ct.observation_interval(sensor, year, s)[2] for s in range(1, 24)]
    return [t for t in tags if through is None or t <= through.replace("-", "")]


def chunk_months(a, b):
    return [f"{y}{m:02d}" for y in range(a, b + 1) for m in range(1, 13)]


def _rng(name):
    return np.random.default_rng(int.from_bytes(name.encode()[-8:], "little") % (2 ** 32))


def chunk_frame(name, admins, through, *, prefix=None, masked="null", props=True):
    """A PRCP/ET0/PATCH32 chunk table complete through ``through`` (YYYY-MM); later months: days_present short and the
    value column null (``masked='null'``) or absent (``'absent'``)."""
    kind, (a, b), field = FAMILIES.family(name)
    prefix = prefix or field
    rng = _rng(name)
    frame = pd.DataFrame({"admin_code": [str(x) for x in admins]})
    cols = {}
    for tag in chunk_months(a, b):
        y, m = int(tag[:4]), int(tag[4:])
        days = pd.Period(f"{y}-{m:02d}").days_in_month
        complete = f"{y}-{m:02d}" <= through
        first_open = str(pd.Period(through, "M") + 1) == f"{y}-{m:02d}"
        cols[f"days_present_{tag}"] = days if complete else (days - 1 if first_open else 0)   # missing its last day
        if complete:
            cols[f"{prefix}_{tag}_mean"] = (rng.gamma(2.0, 40.0, len(admins)) if prefix == "prcp"
                                            else rng.uniform(60, 160, len(admins)))
        elif masked == "null":
            cols[f"{prefix}_{tag}_mean"] = [None] * len(admins)
    frame = pd.concat([frame, pd.DataFrame(cols)], axis=1)
    if props:
        job = job_for(name)
        frame = frame.assign(**expected_props(job))
    return frame


def vi_frame(name, admins, through=None, *, composites=None):
    kind, (year, _), _ = FAMILIES.family(name)
    sensor = next(s for s, cfg in tp.VI_SOURCES.items() if f"_{cfg['label']}_" in name)
    tags = composites if composites is not None else vi_tags(sensor, year, through)
    rng = _rng(name)
    frame = pd.DataFrame({"admin_code": [str(x) for x in admins]})
    cols = {}
    for t in tags:
        for f in ("evi", "ndvi", "used1km"):
            cols[f"{f}_{t}_mean"] = rng.uniform(0.25, 0.35, len(admins)) if f != "used1km" else 16.0
    frame = pd.concat([frame, pd.DataFrame(cols)], axis=1)
    return frame.assign(**expected_props(job_for(name)), composite_dates=",".join(tags))


def job_for(name):
    kind, years, field = FAMILIES.family(name)
    if kind == "vi":
        sensor = next(s for s, cfg in tp.VI_SOURCES.items() if f"_{cfg['label']}_" in name)
        return tp.TableJob(name, "vi", sensor, years)
    if "PATCH32" in name:
        return tp.TableJob(name, "patch32", None, years)
    if field == "et0":
        return tp.TableJob(name, "et0", None, years)
    return tp.TableJob(name, "prcp", next(s for s, lab in ct.SPI_SOURCES.items() if f"_{lab}_" in name), years)


def expected_props(job):
    if job.kind == "vi":
        cfg = tp.VI_SOURCES[job.key]
        return {"sensor": cfg["label"], "product": cfg["collection"], "observation_year": job.years[0],
                "temporal_resolution": "16_day", "spatial_product": "CMG_0P05_DEG"}
    a, b = job.years
    out = {"chunk_start_year": a, "chunk_end_year": b, "temporal_resolution": "monthly_total", "unit": "mm_month"}
    if job.kind == "prcp":
        return {**out, "source": ct.SPI_SOURCES[job.key], "product": tp.PRECIP_SOURCES[job.key]["collection"]}
    out.update({"source": tp.ET0_SOURCE, "product": tp.ERA5_DAILY_ID, "et0_method": tp.ET0_METHOD})
    if job.kind == "patch32":
        out.update({"et0_spatial_fallback": 1, "fallback_method": "BUFFERED_ERA5LAND_MEAN", "fallback_buffer_m": 30000,
                    "patch_version": "V2"})
    return out


def static_world(admins, *, static_through="2026-08"):
    """The shared read-only inputs: 25 admin partitions, VI baselines, the historical drought chunks and the existing
    (stale) 2020-2026 chunk / 2026 VI tables at the han-sandbox root."""
    world = {a: pd.DataFrame({"admin_code": []}) for a in AssetRefs().admins()}
    for label in ("TERRA", "AQUA"):
        rows = pd.DataFrame({"admin_code": [str(x) for x in admins],
                             **{f"evi_base_s{s:02d}_mean": 0.2 for s in range(1, 24)}})
        for part in range(1, 5):
            world[REFS.asset(REFS.vi_baseline.format(label=label, part=part))] = rows   # non-empty, as the real parts
        name = REFS.vi_current.format(label=label, year=2026)
        world[REFS.asset(name)] = vi_frame(name, admins, static_through)
    for a, b in REFS.year_chunks:
        for name in [REFS.prcp.format(label=lab, a=a, b=b) for lab in ct.SPI_SOURCES.values()] + [REFS.et0.format(a=a, b=b)]:
            world[REFS.asset(name)] = chunk_frame(name, admins, static_through, props=False)
        patch = REFS.et0_patch.format(a=a, b=b)
        world[REFS.asset(patch)] = chunk_frame(patch, [str(c) for c in tp.PATCH32_CODES], static_through, props=False)
    return world


def server_for(admins, *, through, vi_through=None, overrides=None):
    """Completed-task table of a produced asset: chunks complete through ``through``, VI composites through
    ``vi_through``; ``overrides[basename] -> frame`` replaces a table (malformed-output tests)."""
    def server(asset_id):
        name = asset_id.rsplit("/", 1)[-1].split("__")[0]
        if overrides and name in overrides:
            return overrides[name]
        kind, _, _ = FAMILIES.family(name)
        if kind == "vi":
            return vi_frame(name, admins, vi_through or through)
        codes = [str(c) for c in tp.PATCH32_CODES] if "PATCH32" in name else admins
        return chunk_frame(name, codes, through)
    return server


class WorldEE:
    """The ``ee`` module seen by ``EETransport``: real offline graph construction, faked server calls."""

    def __init__(self, world, server, *, states=("COMPLETED",), patch_count=None, start_error=None, missing_after=()):
        real = offline_ee()
        self._real, self.world, self.server, self.tasks, self.deadlines, self.events = real, world, server, [], [], []
        self.calls = []                 # (request, deadline_ms, max_retries) in effect for every faked server request
        self.missing_after = set(missing_after)
        proxy = self
        count = patch_count or {"rows": 32, "unique_codes": 32}

        class State:
            deadline_ms, max_retries = 0, 5                    # the SDK defaults

        state = State()

        def call(name):
            proxy.calls.append((name, state.deadline_ms, state.max_retries))
        self._call, self.state = call, state

        class Data:
            def _get_state(self):
                return state

            def setDeadline(self, ms):
                state.deadline_ms = ms
                proxy.deadlines.append(ms)

            def setMaxRetries(self, n):
                state.max_retries = n

            def getAsset(self, asset_id):
                call("getAsset")
                if asset_id in proxy.world:
                    return {"name": asset_id, "type": "TABLE"}
                raise Exception(AMBIGUOUS.format(asset_id))

            def listAssets(self, params):
                call("listAssets")
                names = sorted(n for n in proxy.world if n.startswith(params["parent"] + "/"))
                size, start = int(params["pageSize"]), int(params.get("pageToken") or 0)
                out = {"assets": [{"name": n} for n in names[start:start + size]]}
                if start + size < len(names):
                    out["nextPageToken"] = str(start + size)
                return out

            def computeFeatures(self, params):
                call("computeFeatures")
                text = json.dumps(json.loads(real.serializer.toJSON(params["expression"])))
                hits = [a for a in proxy.world if json.dumps(a)[1:-1] in text]
                return feature_page(proxy.world[max(hits, key=len)], params)

        class Task:
            def __init__(self, kw):
                self.kw, self.id, self.polls = kw, f"T{len(proxy.tasks)}", 0
                self.cancelled = False
                proxy.tasks.append(self)
                proxy.events.append(("submit", self.id))

            def start(self):
                if start_error is not None:
                    raise start_error

            def cancel(self):
                call("cancel")
                self.cancelled = True

            def status(self):
                call("status")
                if self.polls >= MAX_POLLS:
                    raise RunawayPoll(f"task {self.id} polled {self.polls} times: the scenario never terminates")
                proxy.events.append(("poll", self.id))
                st = states[min(self.polls, len(states) - 1)] if not callable(states) else states(self)
                self.polls += 1
                if st == "COMPLETED" and self.kw["assetId"] not in proxy.missing_after:
                    proxy.world.setdefault(self.kw["assetId"], proxy.server(self.kw["assetId"]))
                return {"state": st}

        class Dictionary(real.Dictionary):
            def getInfo(self):
                call("getInfo")
                return dict(count)

        self.data, self.Dictionary = Data(), Dictionary
        self.batch = type("batch", (), {"Export": type("Export", (), {"table": type("table", (), {
            "toAsset": staticmethod(lambda **kw: Task(kw))})})})

    def __getattr__(self, name):
        return getattr(self._real, name)


def exported(ee_world):
    return [t.kw["assetId"] for t in ee_world.tasks]


def basename(asset_id):
    return re.sub(r"__.*$", "", asset_id.rsplit("/", 1)[-1])
