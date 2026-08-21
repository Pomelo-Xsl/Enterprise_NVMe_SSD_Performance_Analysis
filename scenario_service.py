"""High-level service combining config, logs, simulation and persistence."""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

from config import ApplicationConfiguration, load_application_config
from log_setup import configure_logs, log_alerts
from persistence import Repository
from scenario_runner import run_configured_scenario


LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


class ScenarioService:
    def __init__(
        self,
        configuration: ApplicationConfiguration,
        database_path: str | Path = "nvme_analysis.db",
    ) -> None:
        self.configuration = configuration
        self.repository = Repository(database_path)
        self.repository.initialize()
        logging_configuration = configuration.logging
        self.logger = configure_logs(
            directory=logging_configuration.directory,
            level=LOG_LEVELS[logging_configuration.level.upper()],
            max_bytes=logging_configuration.max_bytes,
            backup_count=logging_configuration.backup_count,
        )

    @classmethod
    def from_yaml(
        cls,
        configuration_path: str | Path,
        database_path: str | Path = "nvme_analysis.db",
    ) -> "ScenarioService":
        return cls(
            load_application_config(configuration_path),
            database_path,
        )

    def run(self) -> dict:
        scenario = self.configuration.scenario
        self.logger.info(
            "scenario_started name=%s profile=%s tags=%s",
            scenario.name,
            scenario.profile,
            ",".join(scenario.tags),
        )
        result = run_configured_scenario(self.configuration)
        run_id = self.repository.save_run(result)
        result["run_id"] = run_id
        alert_events = result.get("alerts", {}).get("events", [])
        log_alerts(self.logger, alert_events)
        self.logger.info(
            "scenario_completed run_id=%s samples=%s alerts=%s",
            run_id,
            result.get("sample_count", 0),
            len(alert_events),
        )
        return result

    def describe(self) -> dict:
        return {
            "scenario": asdict(self.configuration.scenario),
            "cache": asdict(self.configuration.cache),
            "workload": asdict(self.configuration.workload),
            "alerts": asdict(self.configuration.alerts),
            "logging": asdict(self.configuration.logging),
        }
