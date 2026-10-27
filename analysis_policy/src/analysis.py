import base64
import logging
import os
from dataclasses import asdict
from datetime import date as Date
from typing import Literal

from privacy_policy_analyzer import Language, UnsupportedLanguage
from privacy_policy_analyzer.analysis.err import ModelLoadError
from privacy_policy_analyzer.config import DEFAULT_CONFIGURATIONS
from privacy_policy_analyzer.crawl import CrawlError
from privacy_policy_analyzer.pipeline import Pipeline, PolicyResult
from privacy_policy_analyzer.report.flow import generate_topic_map
from privacy_policy_analyzer.report.label import LabelConfig, generate_svg_label
from privacy_policy_analyzer.report.readability import calculate_readability_scores
from privacy_policy_analyzer.report.score import create_score_report
from privacy_policy_analyzer.report.summary import create_summary_report
from privacy_policy_analyzer.shared.logging import set_logging
from pydantic import BaseModel

BASE_DIR = "./uploads"
os.makedirs(BASE_DIR, exist_ok=True)


pipeline: Pipeline = Pipeline(
    configs=DEFAULT_CONFIGURATIONS,
    prefer_onnx=False,
    cache_load_models=True,
)

include_contexts: list[str] = []
exclude_contexts: list[str] = []

set_logging(file=None, level=logging.DEBUG)


class AnalysisResult(BaseModel):
    source: str
    language: str
    html: str
    analyzed: list[dict]

    summary: dict
    scores: dict
    topic_map_png: str
    label_svg: str


def analyze_policy(
    type: Literal["html", "url"], content: str, additional: str | None
) -> AnalysisResult | None:
    print(f"Analyzing policy of type: {type}")

    policy: PolicyResult
    name = "Test Policy"

    try:
        if type == "url":
            result: PolicyResult | CrawlError | UnsupportedLanguage | ModelLoadError = (
                pipeline.run_with_url(
                    name=name,
                    url=content,
                    preferred_language=None,
                )
            )

            if not isinstance(result, PolicyResult):
                print(f"Analysis failed for {name}: {result}")

            assert isinstance(result, PolicyResult)
            policy = result

        elif type == "html":
            if not additional:
                print("Source URL must be provided for HTML content.")
                return None

            result_: PolicyResult | UnsupportedLanguage | ModelLoadError = (
                pipeline.run_with_html(
                    name=name,
                    source=additional,
                    language=Language.EN,
                    date=Date.today(),
                    html=content,
                )
            )

            if not isinstance(result_, PolicyResult):
                print(f"Analysis failed for {name}: {result_}")

            assert isinstance(result_, PolicyResult)
            policy = result_

    except Exception as e:
        print(f"Error crawling URL: {e}")
        raise

    summary = create_summary_report(policy.analyzed, include_contexts, exclude_contexts)
    scores = create_score_report(summary)
    readability = calculate_readability_scores(policy.text)
    topic_map_png = generate_topic_map(policy.analyzed)

    config: LabelConfig = LabelConfig(
        grade_data_specificity=True,
        grade_third_party_specificity=True,
        grade_retention_specificity=True,
        grade_readability=True,
        collection_purposes=False,
        coverage_security_measures=True,
        coverage_user_rights=True,
        coverage_merger_acquisition=True,
        coverage_children=True,
        coverage_overall=True,
        contact_info=True,
        meta_info=False, # contact + meta
        meta_overall=False,
        profiling=True,
        automated_decision=True,
        total_collected_data_types=True,
        specific_data_types_collected=False,
        total_shared_data_types=True,
        specific_shared_data_types=True,
        total_third_parties=True,
        specific_third_parties=True,
        total_third_party_types=True,
        specific_third_party_types=True,
        legal_basis=False,
    )
    label_svg = generate_svg_label(scores, summary, readability, policy.source, config)

    topic_map_png_encoded = base64.b64encode(topic_map_png).decode("utf-8")

    analyzed = [asdict(item) for item in policy.analyzed]
    return AnalysisResult(
        source=policy.source,
        language=policy.language,
        html=policy.html,
        analyzed=analyzed,
        summary=asdict(summary),
        scores=asdict(scores),
        topic_map_png=topic_map_png_encoded,
        label_svg=label_svg,
    )
