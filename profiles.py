"""Safe benchmark-profile catalogue and validation helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class BenchmarkProfile:
    key: str
    name: str
    description: str
    rw: str
    block_size: str
    io_depth: int
    jobs: int
    runtime: int
    ramp_time: int
    direct_io: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


CATALOGUE = {
    "burst-write": BenchmarkProfile("burst-write", "短时突发写", "观察缓存阶段的峰值顺序写性能", "write", "1M", 16, 1, 300, 15),
    "sustained-write": BenchmarkProfile("sustained-write", "持续顺序写", "识别缓存耗尽和稳态写入性能", "write", "128K", 32, 1, 1800, 30),
    "random-write": BenchmarkProfile("random-write", "4K 随机写", "评估随机写 IOPS 与尾延迟", "randwrite", "4K", 64, 4, 900, 30),
    "gc-pressure": BenchmarkProfile("gc-pressure", "GC 压力测试", "观察垃圾回收引起的性能波动", "randwrite", "4K", 64, 4, 1800, 60),
    "recovery-probe": BenchmarkProfile("recovery-probe", "恢复能力探测", "压力测试后的低风险恢复采样", "write", "128K", 16, 1, 300, 0),
}

ALLOWED_BLOCK_SIZES = {"4K", "8K", "16K", "32K", "64K", "128K", "256K", "512K", "1M"}
ALLOWED_RW = {"write", "randwrite", "read", "randread", "rw", "randrw"}


def list_profiles() -> list[dict]:
    return [profile.to_dict() for profile in CATALOGUE.values()]


def get_profile(key: str) -> BenchmarkProfile:
    try:
        return CATALOGUE[key]
    except KeyError as error:
        raise ValueError(f"unknown profile: {key}") from error


def apply_profile(key: str, overrides: Mapping | None = None) -> dict:
    result = get_profile(key).to_dict()
    result.update(overrides or {})
    validate_parameters(result)
    return result


def validate_parameters(parameters: Mapping) -> None:
    block_size = parameters.get("block_size")
    if block_size not in ALLOWED_BLOCK_SIZES:
        raise ValueError("unsupported block_size")
    rw = parameters.get("rw", "write")
    if rw not in ALLOWED_RW:
        raise ValueError("unsupported rw mode")
    for field, minimum, maximum in (("io_depth", 1, 256), ("jobs", 1, 32), ("runtime", 30, 7200), ("ramp_time", 0, 600)):
        value = parameters.get(field)
        if not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{field} must be an integer between {minimum} and {maximum}")


def safe_fio_preview(profile: Mapping, device: str) -> list[str]:
    """Return a preview only—this project never executes the resulting command."""
    validate_parameters(profile)
    return ["fio", "--name=nvme-insight-preview", f"--filename={device}", f"--rw={profile['rw']}", f"--bs={profile['block_size']}", f"--iodepth={profile['io_depth']}", f"--numjobs={profile['jobs']}", f"--runtime={profile['runtime']}", f"--ramp_time={profile['ramp_time']}", "--direct=1", "--output-format=json+"]
