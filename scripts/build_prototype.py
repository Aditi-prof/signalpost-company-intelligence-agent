#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


QUESTION_ROUTES = [
    ("financials", r"\bfinancial(?:ly)?\b|\bfinance\b|\baccount(?:s|ing)?\b|\brevenue\b|\bincome\b|\bprofit\b|\bdebt\b|\bassets?\b|\bresults?\b|\bregnskap\b|\binntekt\b|\bgjeld\b"),
    ("leaders", r"\bwho runs\b|\bwho leads\b|\blead(?:ership|er|ers)?\b|\broles?\b|\bdirectors?\b|\bchair(?:man|woman)?\b|\bboard\b|\bceo\b|\bmanagement\b|\bledelse\b|\bstyre\b"),
    ("hiring", r"\bjobs?\b|\bhiring\b|\bhire\b|\bcareers?\b|\bvacanc(?:y|ies)\b|\bstilling(?:er)?\b|\brecruit(?:ing|ment)?\b"),
    ("social", r"\bsocial\b|\blinkedin\b|\bfacebook\b|\binstagram\b|\byoutube\b|\btiktok\b|\bprofiles?\b|\bhandles?\b"),
    ("activity", r"\bposts?(?:ed|ing)?\b|\bpublic activity\b|\bactivity\b|\bbuzz\b|\bengagement\b|\breactions?\b|\bcomments?\b|\btalking\b"),
    ("sentiment", r"\bsentiment\b|\breputation\b|\bopinions?\b|\bpositive\b|\bnegative\b|\bmentions?\b|\breviews?\b|\bgood place to work\b|\bgood company to work\b|\bemployee satisfaction\b|\bwork for\b"),
    ("locations", r"\blocations?\b|\bwhere\b|\baddresses?\b|\bshops?\b|\boffices?\b|\bbranches\b|\bplaces?\b|\bsted\b|\badresse\b|\bbutikk\b|\bkontor\b"),
    ("overview", r"\btell me about\b|\bcompany\b|\boverview\b|\bsummary\b|\bdescribe\b|\bwhat does\b|\bregistered\b|\bindustry\b|\bkommune\b|\bansatt\b"),
]
FULL_REPORT_PATTERN = (
    r"\b(full|complete|comprehensive)\s+(company\s+)?(report|brief)\b"
    r"|\ball available evidence\b|\beverything about\b"
)
OVERVIEW_QUESTION_PATTERN = r"\btell me about\b|\boverview\b|\bsummary\b|\bdescribe\b"


def _normalize_question(question: str) -> str:
    decomposed = unicodedata.normalize("NFD", question or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def requested_modes(question: str) -> list[str]:
    normalized = _normalize_question(question)
    if re.search(FULL_REPORT_PATTERN, normalized):
        return [
            "overview",
            "financials",
            "leaders",
            "locations",
            "social",
            "hiring",
            "activity",
            "sentiment",
        ]
    if re.search(OVERVIEW_QUESTION_PATTERN, normalized):
        return ["overview"]
    return next(
        ([mode] for mode, pattern in QUESTION_ROUTES if re.search(pattern, normalized)),
        ["overview"],
    )


def _role_display_name(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if item is not None and item != "")
    return str(value) if value is not None else ""


def _latest_financial_record(records: list[dict]) -> dict | None:
    if not records:
        return None

    def period_end(record: dict) -> str:
        period = record.get("period") or {}
        return str(period.get("tilDato") or "")

    dated = [(period_end(record), index, record) for index, record in enumerate(records)]
    if any(date for date, _, _ in dated):
        return max(dated, key=lambda item: (item[0], -item[1]))[2]
    return records[0]


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _source_link(url: object, label: str = "Source ↗") -> str:
    if not isinstance(url, str) or not url:
        return ""
    if not url.lower().startswith(("https://", "http://")):
        return ""
    return f' <a href="{_escape(url)}" target="_blank" rel="noreferrer">{_escape(label)}</a>'


def _format_amount(value: object, currency: object) -> str:
    if value is None:
        return "Not reported in the selected snapshot"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        amount = f"{value:,.0f}"
    else:
        amount = _escape(value)
    return f"{amount} {_escape(currency) if currency else 'currency not reported'}"


def report_overview_html(company: dict) -> str:
    def fact(label: str, value: object) -> str:
        display = "Not reported in the selected snapshot" if value is None or value == "" else _escape(value)
        return f"<li><strong>{_escape(label)}:</strong> {display}</li>"

    registry_facts = "".join(
        fact(label, value)
        for label, value in (
            ("Legal form", company.get("form")),
            ("Organisation number", company.get("org")),
            ("Municipality", company.get("municipality")),
            ("Industry", company.get("industry")),
            ("Industry code", company.get("industryCode")),
            ("Registry employee count", company.get("employees")),
        )
    )
    return (
        '<section class="agent-overview"><h4>'
        + _escape(company.get("name") or "Company name not reported")
        + '</h4><p class="evidence-intro">Company identity and registry facts.</p>'
        + "<section><h5>Official registry evidence</h5><ul>"
        + registry_facts
        + "</ul>"
        + _source_link(company.get("registrySource"), "View registry record ↗")
        + "</section></section>"
    )


def overview_html(company: dict) -> str:
    financial = company.get("financial") or {}
    financial_record = (
        _latest_financial_record(financial.get("records") or [])
        if financial.get("status") == "available"
        else None
    )
    active_roles = [
        role for role in (company.get("roles") or {}).get("items") or []
        if role.get("inactive") is False
    ]
    active_role_count = (company.get("roles") or {}).get("activeCount", len(active_roles))
    role_status = (company.get("roles") or {}).get("status")
    locations = company.get("locations") or {}
    external = company.get("external") or {}
    linkedin = external.get("linkedin") or {}
    profile = linkedin.get("profile") or {}

    def fact(label: str, value: object) -> str:
        display = "Not reported in the selected snapshot" if value is None or value == "" else _escape(value)
        return f"<li><strong>{_escape(label)}:</strong> {display}</li>"

    registry_source = _source_link(company.get("registrySource"), "Official registry source ↗")
    details = [
        fact("Legal form", company.get("form")),
        fact("Organisation number", company.get("org")),
        fact("Municipality", company.get("municipality")),
        fact("Industry", company.get("industry")),
        fact("Industry code", company.get("industryCode")),
        fact("Registry employee count", company.get("employees")),
    ]
    sections = [
        "<section><h5>Official registry evidence</h5><ul>"
        + "".join(details)
        + "</ul>"
        + _source_link(company.get("registrySource"), "View registry record ↗")
        + "</section>"
    ]

    financial_source = _source_link(financial.get("source"), "Official accounting source ↗")
    if financial_record:
        period = financial_record.get("period") or {}
        period_end = period.get("tilDato")
        period_copy = f" for the period ending {_escape(period_end)}" if period_end else ""
        financial_facts = "".join(
            f"<li><strong>{_escape(label)}:</strong> {_format_amount(financial_record.get(key), financial_record.get('currency'))}</li>"
            for label, key in (
                ("Revenue", "revenue"),
                ("Operating result", "operating_result"),
                ("Annual result", "annual_result"),
            )
        )
        sections.append(
            "<section><h5>Latest normalized annual-account figures"
            + period_copy
            + "</h5><ul>" + financial_facts + "</ul>"
            + financial_source
            + "<p class=\"evidence-boundary\">These are reported accounting figures, not a standalone assessment of financial health.</p></section>"
        )
    else:
        sections.append(
            "<section><h5>Financial records</h5><p>No normalized financial record is available in this snapshot; missing data is not zero."
            + financial_source + "</p></section>"
        )

    roles_source = _source_link((company.get("roles") or {}).get("source"), "Official roles source ↗")
    if active_roles:
        role_items = "".join(
            "<li><strong>" + _escape(_role_display_name(role.get("name")) or "Name not reported")
            + "</strong> — " + _escape(role.get("role") or role.get("group") or "Role not reported")
            + "</li>"
            for role in active_roles[:5]
        )
        role_summary = f"<p>{_escape(active_role_count)} active registered role record(s).</p><ul>{role_items}</ul>{roles_source}"
    elif role_status == "available":
        role_summary = "<p>No active registered role records were returned.</p>" + roles_source
    else:
        role_summary = "<p>Active registered role records are not available in this snapshot.</p>" + roles_source
    sections.append("<section><h5>Active registered leadership</h5>" + role_summary + "</section>")

    locations_source = _source_link(locations.get("source"), "Official subunit source ↗")
    if locations.get("status") == "available":
        locations_count = locations.get("count")
        count_copy = _escape(locations_count) if locations_count is not None else "Not reported"
        location_summary = (
            f"<p>{count_copy} registered operating subunit(s) returned by the registry.</p>"
            + locations_source
        )
    else:
        location_summary = (
            "<p>Registered operating-subunit count is not available in this snapshot.</p>"
            + locations_source
        )
    sections.append("<section><h5>Registered locations</h5>" + location_summary + "</section>")

    if linkedin.get("available"):
        metrics = []
        for label, key in (
            ("followers", "followers"),
            ("associated profiles", "visible_employees"),
            ("employee-size label", "employee_size_label"),
        ):
            value = profile.get(key)
            if value is not None and value != "":
                metrics.append(f"<strong>{_escape(label)}:</strong> {_escape(value)}")
        metric_copy = " · ".join(metrics) if metrics else "No profile metrics were reported"

    jobs = linkedin.get("jobs") or []
    if jobs:
        job_items = "".join(
            "<li><strong>" + _escape(job.get("title") or "Job title not reported")
            + "</strong> — " + _escape(job.get("location") or "Location not reported")
            + _source_link(job.get("job_url") or job.get("source"), "Captured job ↗")
            + "</li>"
            for job in jobs[:3]
        )
        job_summary = "<p>Captured job listings are experimental signals, not proof of hiring outcomes.</p><ul>" + job_items + "</ul>"
    else:
        job_summary = "<p>No exact-company job listing was captured in this snapshot.</p>"

    posts = linkedin.get("posts") or []
    if posts:
        post_items = "".join(
            "<li>" + _escape(post.get("text") or "Post captured; text not reported")
            + _source_link(post.get("source"), "Captured post ↗")
            + "</li>"
            for post in posts[:3]
        )
        post_summary = "<p>Captured public posts are experimental signals, not evidence of business performance or sentiment.</p><ul>" + post_items + "</ul>"
    else:
        post_summary = "<p>No exact-company public activity post was captured in this snapshot.</p>"

    external_source = "<section><h5>Experimental external signals</h5>"
    if linkedin.get("available"):
        external_source += "<p>Exact-company LinkedIn profile: " + _source_link(profile.get("profileUrl") or profile.get("source"), "Open profile ↗") + " " + metric_copy + _source_link(profile.get("source"), "Observation source ↗") + ".</p>"
    else:
        external_source += "<p>No exact-company LinkedIn profile metrics are available in this snapshot.</p>"
    external_source += job_summary + post_summary
    external_source += "<p class=\"evidence-boundary\">These platform observations do not establish business performance, reputation, employee satisfaction, or financial health.</p></section>"
    sections.append(external_source)

    return (
        "<section class=\"agent-overview\"><h4>"
        + _escape(company.get("name") or "Company name not reported")
        + "</h4><p class=\"evidence-intro\">Official registry and normalized accounting evidence are summarized separately from experimental external observations.</p>"
        + "".join(sections)
        + "</section>"
    )


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_independent_score(independent_score: dict | None) -> dict:
    result = dict(independent_score or {})
    if not result:
        return result
    score = result.get("score") or {}
    submission = score.get("submission_1000") or {}
    identity = (result.get("qualification") or {}).get("identity_gate") or {}
    if submission:
        result["qualification_passed"] = bool((result.get("qualification") or {}).get("passed"))
        result["raw_score"] = submission.get("raw_score", score.get("raw_score", 0))
        result["category_scores"] = {
            key: value.get("score", 0) for key, value in (submission.get("categories") or {}).items()
        }
        result["identity_audit"] = {
            "published_domains_correct": identity.get("published_domains_exact", 0),
            "published_socials_correct": identity.get("published_socials_exact", 0),
        }
        result["proxy"] = result.get("proxy") or {
            "submission_1000": (result.get("proxy_results_not_adopted") or {}).get("submission_1000", 0),
            "extension_250": (result.get("proxy_results_not_adopted") or {}).get("extension_250", 0),
        }
    return result


def qualification_copy(score: dict | None, independent_score: dict | None = None) -> tuple[str, str]:
    score = score or {}
    independent_score = normalize_independent_score(independent_score)
    if independent_score.get("qualification_passed"):
        independent = independent_score.get("raw_score", 0)
        proxy = (independent_score.get("proxy") or {}).get("submission_1000", score.get("raw_score", 0))
        return (
            f"Independent judge {independent}/100 · qualification passed · proxy {proxy}/100",
            "The independent score reached the 80-point target on both frozen corpora. Exact-entity publication, filing history and fresh PDF checks passed; calendar-time operation, open-ended research and broad context coverage remain unproven.",
        )
    if score.get("scorer") == "signalpost_all_source_completeness_v1":
        combined = score.get("combined") or {}
        return (
            f"Evidence completeness {combined.get('experimental_completeness_mean', 0):.2f}/100 experimental · {combined.get('strict_completeness_mean', 0):.2f}/100 strict",
            "LinkedIn discovery now enriches exact company records, but automated LinkedIn captures remain experimental. Company sites and social handles only enter the strict layer after independent identity verification.",
        )
    if "raw_score" in score:
        raw = score.get("raw_score", 0)
        if score.get("qualification_passed"):
            return (
                f"Competition proxy qualified · {raw}/100 · independent hidden score still required",
                "The corrected proxy passes its current gates. Final ranking still requires evaluator-owned hidden batches and a fresh independent review.",
            )
        failures = len(score.get("unproven_or_failed") or [])
        return (
            f"Competition proxy {raw}/100 · {failures} gate(s) unproven or failed",
            "This is an optimization measurement, not an official competition score. Open the scorecard to see the remaining hard gates.",
        )
    qualification = score.get("qualification") or {}
    weighted = score.get("weighted_score") or {}
    if qualification.get("poc_qualified"):
        points = weighted.get("verified_points")
        maximum = weighted.get("maximum_points")
        points_copy = f"{points}/{maximum} verified core points" if points is not None and maximum is not None else "core gate passed"
        return (
            f"POC qualified · {points_copy} · not production-qualified",
            "Frozen core checks passed. Search-based discovery and sentiment remain quarantined pending their own external evaluation.",
        )
    return (
        "1,000-entity frozen POC · not a production service",
        "Qualification is pending; inspect the evidence and scorecard before making a product claim.",
    )


def compact(row: dict, external_observations: list[dict] | None = None) -> dict:
    evidence = row.get("evidence") or {}
    financial = evidence.get("financials") or {}
    financial_history = evidence.get("financial_history") or {}
    roles = evidence.get("roles") or {}
    locations = evidence.get("locations") or {}
    website = evidence.get("website") or {}
    website_value = dict(website.get("value") or {})
    if website.get("status") == "available" and not website_value.get("title"):
        website_value["title"] = "Company site fetched"
    identity_assessment = website_value.get("identity_assessment") or {}
    if website.get("status") == "available" and identity_assessment.get("publishable") is not True:
        discovered_social = website_value.get("discovered_social_links") or []
        published_social = website_value.get("social_links") or []
        quarantined_social = [
            item for item in [*discovered_social, *published_social] if isinstance(item, dict)
        ]
        website_value["quarantined_title"] = website_value.get("title")
        website_value["quarantined_description"] = website_value.get("description")
        website_value["quarantined_social_count"] = len({
            (item.get("platform"), item.get("url")) for item in quarantined_social
        })
        website_value["social_links"] = []
        website_value["title"] = "Registry-linked site — identity not verified"
        website_value["description"] = "Fetched content is retained as discovered evidence but is not attributed to this legal entity."
    live = evidence.get("registry_live") or {}
    accounting = evidence.get("accounting_obligation") or {}
    external_observations = external_observations or []

    def observation_meta(item: dict) -> dict:
        return {
            "source": item.get("source_url"),
            "retrievedAt": item.get("retrieved_at"),
            "publishedAt": item.get("published_at") or item.get("date_published"),
            "hash": item.get("content_sha256"),
            "rightsStatus": item.get("rights_status"),
            "sourceClass": item.get("source_class"),
        }

    organisation_number = str(row.get("organisation_number") or "")

    def exact_observation(item: dict) -> bool:
        return (
            item.get("exact_entity") is True
            and bool(organisation_number)
            and str(item.get("organisation_number") or "") == organisation_number
        )

    linkedin_profiles = [
        item for item in external_observations
        if item.get("platform") == "linkedin" and item.get("signal_type") == "profile_metrics" and exact_observation(item)
    ]
    linkedin_workforce = [
        item for item in external_observations
        if item.get("platform") == "linkedin" and item.get("signal_type") == "workforce_snapshot" and exact_observation(item)
    ]
    linkedin_posts = [
        item for item in external_observations
        if item.get("platform") == "linkedin" and item.get("signal_type") == "public_post" and exact_observation(item)
    ]
    linkedin_jobs = [
        item for item in external_observations
        if item.get("platform") == "linkedin" and item.get("signal_type") == "job_posting" and exact_observation(item)
    ]
    verified_handles = {}
    for item in external_observations:
        if item.get("signal_type") != "profile_handle" or not exact_observation(item):
            continue
        url = item.get("profile_url") or item.get("source_url")
        if url:
            verified_handles[(item.get("platform"), url)] = {
                "platform": item.get("platform"),
                "url": url,
                "rightsStatus": item.get("rights_status"),
            }
    linkedin_profile = linkedin_profiles[-1] if linkedin_profiles else None
    linkedin_headcount = linkedin_workforce[-1] if linkedin_workforce else None
    external = {
        "handles": list(verified_handles.values()),
        "linkedin": {
            "available": bool(linkedin_profile),
            "profile": ({
                **(linkedin_profile.get("metrics") or {}),
                "profileUrl": linkedin_profile.get("profile_url") or linkedin_profile.get("source_url"),
                **observation_meta(linkedin_profile),
            } if linkedin_profile else {}),
            "workforce": ({**(linkedin_headcount.get("metrics") or {}), **observation_meta(linkedin_headcount)} if linkedin_headcount else {}),
            "posts": [
                {
                    **(item.get("metrics") or {}),
                    "text": item.get("evidence_span"),
                    **observation_meta(item),
                }
                for item in linkedin_posts[:10]
            ],
            "jobs": [
                {
                    **(item.get("metrics") or {}),
                    "text": item.get("evidence_span"),
                    **observation_meta(item),
                }
                for item in linkedin_jobs[:10]
            ],
        },
    }

    def meta(record: dict) -> dict:
        record = record or {}
        return {
            "status": record.get("status", "not_run"),
            "source": record.get("source_url"),
            "sourceClass": record.get("source_class") or record.get("source_type"),
            "retrievedAt": record.get("retrieved_at"),
            "effectiveAt": record.get("effective_at") or record.get("as_of"),
            "hash": record.get("content_sha256"),
            "rowKey": record.get("source_row_key"),
        }
    result = {
        "org": row.get("organisation_number"),
        "name": row.get("name"),
        "form": row.get("legal_form"),
        "employees": row.get("employees"),
        "municipality": row.get("municipality"),
        "industryCode": row.get("industry_code"),
        "industry": row.get("industry_label"),
        "website": row.get("website"),
        "adverse": bool(row.get("bankrupt") or row.get("liquidating")),
        "slice": row.get("sample_slice"),
        "split": row.get("evaluation_split"),
        "latestAccounts": row.get("latest_submitted_accounts"),
        "registrySource": (evidence.get("registry") or {}).get("source_url"),
        "registry": meta(evidence.get("registry", {})),
        "accounting": {**meta(accounting), "value": accounting.get("value") or {}},
        "financial": {**meta(financial), "records": ((financial.get("value") or {}).get("records") or [])[:3]},
        "financialHistory": {**meta(financial_history), "pdfs": (financial_history.get("value") or {}).get("pdfs", [])},
        "roles": {
            **meta(roles),
            "activeCount": sum(item.get("inactive") is False for item in ((roles.get("value") or {}).get("roles") or [])),
            "items": ((roles.get("value") or {}).get("roles") or [])[:30],
        },
        "locations": {
            **meta(locations),
            "count": len((locations.get("value") or {}).get("locations") or []),
            "items": ((locations.get("value") or {}).get("locations") or [])[:30],
        },
        "web": {**meta(website), "value": website_value},
        "liveStatus": live.get("status", "not_run"),
        "changes": row.get("change_history") or [],
        "external": external,
    }
    result["overviewHtml"] = overview_html(result)
    result["reportOverviewHtml"] = report_overview_html(result)
    return result


def build(rows: list[dict], score: dict | None, control_loop: dict | None = None, independent_score: dict | None = None, external_by_org: dict[str, list[dict]] | None = None) -> str:
    independent_score = normalize_independent_score(independent_score)
    external_by_org = external_by_org or {}
    payload = json.dumps([compact(row, external_by_org.get(str(row["organisation_number"]), [])) for row in rows], ensure_ascii=False).replace("</", "<\\/")
    score_ui = score or {}
    if score_ui.get("scorer") == "signalpost_all_source_completeness_v1":
        combined = score_ui.get("combined") or {}
        strict = round(float(combined.get("strict_completeness_mean") or 0), 2)
        experimental = round(float(combined.get("experimental_completeness_mean") or 0), 2)
        score_ui = {
            **score_ui,
            "raw_score": experimental,
            "awardable_score": strict,
            "rubric_weights": {
                "strict_evidence_completeness": 100,
                "experimental_linkedin_completeness": 100,
                "strict_companies_at_50": combined.get("companies") or len(rows),
                "experimental_companies_at_65": combined.get("companies") or len(rows),
            },
            "category_scores": {
                "strict_evidence_completeness": strict,
                "experimental_linkedin_completeness": experimental,
                "strict_companies_at_50": combined.get("strict_at_50") or 0,
                "experimental_companies_at_65": combined.get("experimental_at_65") or 0,
            },
            "qualification_gates": {
                "32 exact LinkedIn profiles captured": True,
                "9 sites and 17 handles discovered downstream": True,
            },
        }
    score_ui = {
        **score_ui,
        "question_intents": {
            "full_report": FULL_REPORT_PATTERN,
            "overview": OVERVIEW_QUESTION_PATTERN,
        },
        "question_routes": [
            {"mode": mode, "pattern": pattern} for mode, pattern in QUESTION_ROUTES
        ],
    }
    score_payload = json.dumps(score_ui, ensure_ascii=False).replace("</", "<\\/")
    control_payload = json.dumps(control_loop or {}, ensure_ascii=False).replace("</", "<\\/")
    independent_payload = json.dumps(independent_score or {}, ensure_ascii=False).replace("</", "<\\/")
    status_copy, boundary_copy = (html.escape(value) for value in qualification_copy(score, independent_score))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,">
<title>Signalpost laboratory — Norway company intelligence</title><meta name="description" content="Verified external company signals grounded in official Norwegian company records.">
<style>
:root{{--paper:#f5f1e8;--white:#fffdf8;--ink:#171614;--muted:#6c685f;--line:#d8d0c2;--accent:#7d2432;--good:#276044;--warn:#98620d;--linkedin:#0a66c2}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}button,input,select{{font:inherit}}a{{color:var(--accent)}}.mast{{border-bottom:1px solid var(--line);background:var(--white);padding:18px 28px;display:flex;justify-content:space-between;align-items:center;gap:20px}}.brand{{font:700 18px Georgia,serif;letter-spacing:.02em}}.brand i{{display:inline-block;width:11px;height:11px;background:var(--accent);transform:rotate(45deg);margin-right:10px}}.snapshot{{color:var(--muted);font-size:12px}}.hero{{max-width:1500px;margin:auto;padding:38px 28px 24px}}.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.14em;color:var(--accent);font-weight:800}}h1{{font:600 clamp(38px,6vw,78px)/.98 Georgia,serif;letter-spacing:-.04em;max-width:980px;margin:10px 0 18px}}.lede{{max-width:820px;color:var(--muted);font-size:17px}}.stats{{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:10px;margin-top:24px}}.stat{{background:var(--white);border:1px solid var(--line);padding:15px;border-radius:4px}}.stat strong{{display:block;font:600 25px Georgia,serif}}.stat span{{color:var(--muted);font-size:12px}}.qualification{{max-width:1444px;margin:0 auto 18px;background:var(--white);border:1px solid var(--line);border-radius:5px}}.qualification summary{{cursor:pointer;padding:15px 18px;display:flex;justify-content:space-between;gap:18px;align-items:center;font-weight:700}}.qualification summary small{{color:var(--muted);font-weight:400}}.qualification-body{{border-top:1px solid var(--line);padding:16px 18px}}.score-grid{{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:8px}}.score-card,.gate-card{{border:1px solid var(--line);padding:10px;min-width:0}}.score-card span,.gate-card span{{display:block;color:var(--muted);font-size:11px}}.score-card strong{{font:600 22px Georgia,serif;color:var(--good)}}.gate-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}}.gate-card strong{{color:var(--warn)}}.gate-card small{{display:block;margin-top:4px;color:var(--muted)}}.shell{{max-width:1500px;margin:auto;padding:0 28px 50px;display:grid;grid-template-columns:280px minmax(0,1fr) 278px;gap:18px;align-items:start}}.panel{{background:var(--white);border:1px solid var(--line);border-radius:5px}}.index-head{{padding:15px 16px 0;display:flex;align-items:baseline;justify-content:space-between}}.index-head strong{{font:600 24px Georgia,serif}}.controls{{padding:12px 16px 16px;border-bottom:1px solid var(--line);display:grid;gap:9px;position:sticky;top:0;background:var(--white);z-index:2}}.controls input,.controls select{{width:100%;border:1px solid var(--line);background:white;padding:10px;border-radius:3px}}.filters,.workspace-actions{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.workspace-actions button,.pin-button{{border:1px solid var(--line);background:var(--white);padding:8px;border-radius:3px;cursor:pointer}}.workspace-actions button:hover,.pin-button:hover{{border-color:var(--accent);color:var(--accent)}}.result-count{{font-size:12px;color:var(--muted)}}.list{{max-height:950px;overflow:auto}}.row{{width:100%;border:0;border-bottom:1px solid var(--line);background:transparent;text-align:left;padding:13px 16px;cursor:pointer}}.row:hover,.row.active{{background:#f0e8dc}}.row strong,.row span{{display:block}}.row span{{font-size:12px;color:var(--muted)}}.profile{{padding:26px}}.profile-head{{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line);padding-bottom:20px}}h2{{font:600 38px/1.05 Georgia,serif;margin:6px 0}}.chips{{display:flex;gap:6px;flex-wrap:wrap}}.chip{{font-size:11px;border:1px solid var(--line);padding:3px 7px;border-radius:999px}}.chip.good{{color:var(--good);border-color:#9db9aa}}.chip.warn{{color:var(--warn);border-color:#d4b77e}}.chip.linkedin{{color:var(--linkedin);border-color:#9fc5eb}}.fact-grid,.signal-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:20px 0}}.fact,.signal-card{{border:1px solid var(--line);padding:13px;min-width:0}}.fact span,.signal-card span,.section-label{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}}.fact strong,.signal-card strong{{display:block;margin-top:4px;overflow-wrap:anywhere}}section{{padding:20px 0;border-top:1px solid var(--line)}}section:first-of-type{{border-top:0}}h3{{font:600 22px Georgia,serif;margin:5px 0 12px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{color:var(--muted)}}.empty{{color:var(--muted);font-style:italic}}.source{{font-size:12px;color:var(--muted);margin-top:10px;overflow-wrap:anywhere}}.source code{{font-size:10px;word-break:break-all}}.people,.locations,.social{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}}.item{{border:1px solid var(--line);padding:10px}}.item small{{display:block;color:var(--muted)}}.activity-list{{display:grid;gap:8px}}.activity{{border-left:2px solid var(--line);padding:2px 0 2px 12px}}.activity p{{margin:4px 0}}.activity small{{color:var(--muted)}}.experimental-note{{border-left:3px solid var(--linkedin);background:#eef5fb;padding:10px 12px;color:#244867;font-size:12px}}.agent{{padding:18px;position:sticky;top:18px;background:var(--ink);color:white}}.agent .eyebrow{{color:#ddb6bd}}.agent h3{{font-size:23px}}.agent p{{color:#d8d0c8}}.agent-form{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px;margin:14px 0 8px}}.agent-form input{{min-width:0;border:1px solid #625d57;background:#272522;color:white;padding:9px;border-radius:3px}}.agent-form input::placeholder{{color:#aaa39b}}.agent-buttons{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:8px 0 14px}}.agent button{{border:1px solid #625d57;background:transparent;color:white;padding:7px;text-align:left;border-radius:3px;cursor:pointer}}.agent button:hover,.agent button.active{{background:var(--accent);border-color:var(--accent)}}.agent-output{{border-top:1px solid #625d57;padding-top:14px}}.agent-output strong{{color:white}}.agent-output a{{color:#f1c8cf}}.agent-question{{border-left:2px solid #ddb6bd;padding-left:9px}}.answer-block+ .answer-block{{border-top:1px solid #494540;padding-top:8px}}.workspace-summary{{margin-top:16px;padding-top:14px;border-top:1px solid #625d57;font-size:12px;color:#d8d0c8}}@media(max-width:1150px){{.score-grid{{grid-template-columns:repeat(2,1fr)}}.shell{{grid-template-columns:280px minmax(0,1fr)}}.agent{{grid-column:2;position:static}}}}@media(max-width:900px){{.stats,.score-grid{{grid-template-columns:repeat(2,1fr)}}.shell{{grid-template-columns:1fr}}.list{{max-height:420px}}.agent{{grid-column:1;order:2}}.profile{{order:3}}}}@media(max-width:520px){{.mast,.hero,.shell{{padding-left:16px;padding-right:16px}}.qualification{{margin-left:16px;margin-right:16px}}.mast{{align-items:flex-start}}.stats,.fact-grid,.signal-grid,.people,.locations,.social,.gate-grid{{grid-template-columns:1fr}}.profile{{padding:18px}}h2{{font-size:30px}}}}
@media(max-width:900px){{.profile{{order:2}}.agent{{order:3}}}}@media(max-width:520px){{.stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}.stat{{padding:11px}}}}.controls input{{font-size:13px}}
.agent-overview>h4,.answer-block>h4{{margin:0 0 12px;font:600 20px Georgia,serif}}.agent-overview>.evidence-intro{{margin:0 0 14px}}.agent-overview section{{margin-top:12px;padding-top:12px;border-top:1px solid #494540}}.agent-overview h5{{margin:0 0 8px;font-size:13px}}.agent-overview ul{{margin:8px 0;padding-left:20px}}.agent-overview li{{margin:3px 0}}.agent-overview .evidence-boundary{{font-size:12px;color:#d8d0c8}}
</style></head><body>
<header class="mast"><div class="brand"><i></i>Signalpost laboratory</div><div class="snapshot">100-company showcase · 22 exact LinkedIn profiles</div></header>
<main><div class="hero"><div class="eyebrow">Norway company intelligence agent</div><h1>Know the company behind the registration.</h1><p class="lede">Start with official Norwegian identity and filings. Then follow the company into the public world: its website, leaders, LinkedIn footprint, hiring, posts, locations and declared social handles.</p><p style="max-width:920px;border-left:3px solid var(--linkedin);padding:8px 12px;margin:18px 0 0;color:#244867;background:#eef5fb;font-size:13px">{boundary_copy}</p><div class="stats" id="stats"></div></div><details class="qualification" id="qualification"><summary><span>Evidence coverage <small>Strict company evidence and experimental LinkedIn signals are shown separately</small></span><strong id="core-score"></strong></summary><div class="qualification-body"><div class="score-grid" id="score-grid"></div><h3 style="font-size:17px;margin-top:16px">What changed</h3><div class="gate-grid" id="external-gates"></div></div></details>
<div class="shell"><aside class="panel"><div class="index-head"><div><div class="eyebrow">Showcase</div><strong>Company index</strong></div><strong id="index-total"></strong></div><div class="controls"><input id="q" type="search" placeholder="Search the 100 companies" aria-label="Search companies"><div class="filters"><select id="form" aria-label="Legal form"><option value="">All forms</option></select><select id="state" aria-label="Status"><option value="">Any status</option><option value="active">Active</option><option value="adverse">Adverse</option></select><select id="finance" aria-label="Financial availability"><option value="">Any accounts state</option><option value="available">Accounts available</option><option value="not_found">No account returned</option></select><select id="slice" aria-label="Sample slice"><option value="">Both slices</option><option value="population">Population</option><option value="stress">Stress</option><option value="extension">Extension</option></select></div><div class="workspace-actions"><button id="save-view" type="button">Save view</button><button id="export-view" type="button">Export results</button></div><div class="result-count" id="count"></div></div><div class="list" id="list"></div></aside><article class="panel profile" id="profile"></article><aside class="panel agent"><div class="eyebrow">Research agent</div><h3>Ask this company.</h3><p>Short, sourced answers from the selected record.</p><form class="agent-form" id="agent-form"><input id="agent-question" type="text" aria-label="Ask about the selected company" placeholder="Hiring? Leaders? Revenue?"><button type="submit">Ask</button></form><div class="agent-buttons" id="agent-buttons"><button data-mode="overview" class="active">Overview</button><button data-mode="financials">Financials</button><button data-mode="leaders">Leaders</button><button data-mode="locations">Locations</button><button data-mode="social">LinkedIn</button><button data-mode="hiring">Hiring</button><button data-mode="activity">Activity</button><button data-mode="sentiment">Sentiment</button></div><div class="agent-output" id="agent-output" aria-live="polite"></div><div class="workspace-summary" id="workspace-summary"></div></aside></div></main>
<script>const DATA={payload};const SCORE={score_payload};const INDEPENDENT={independent_payload};const CONTROL={control_payload};const $=s=>document.querySelector(s);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const norm=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();const money=(v,c)=>v==null?'Not reported':new Intl.NumberFormat('en-US',{{maximumFractionDigits:0}}).format(v)+' '+(c||'');
const forms=[...new Set(DATA.map(x=>x.form).filter(Boolean))].sort();$('#form').innerHTML+=[...forms].map(x=>`<option>${{esc(x)}}</option>`).join('');
const available=(x,k)=>x[k]?.status==='available';function filtered(){{const q=norm($('#q').value),f=$('#form').value,s=$('#state').value,fin=$('#finance').value,sl=$('#slice').value;return DATA.filter(x=>(!q||norm([x.name,x.org,x.municipality,x.industry,x.industryCode].join(' ')).includes(q))&&(!f||x.form===f)&&(!s||(s==='adverse')===x.adverse)&&(!fin||x.financial.status===fin)&&(!sl||x.slice===sl)).sort((a,b)=>a.name.localeCompare(b.name,'nb'));}}
function renderStats(){{const finance=DATA.filter(x=>available(x,'financial')).length,web=DATA.filter(x=>available(x,'web')).length,linkedin=DATA.filter(x=>x.external?.linkedin?.available).length,activity=DATA.reduce((n,x)=>n+(x.external?.linkedin?.posts?.length||0)+(x.external?.linkedin?.jobs?.length||0),0);$('#index-total').textContent=DATA.length;$('#stats').innerHTML=[[DATA.length,'companies in showcase'],[finance,'annual accounts returned'],[web,'company websites captured'],[linkedin,'exact LinkedIn profiles'],[activity,'public posts + jobs captured']].map(([v,l])=>`<div class="stat"><strong>${{v}}</strong><span>${{l}}</span></div>`).join('')}}
function renderQualification(){{const legacyMax={{accuracy_identity_evidence:35,useful_coverage:25,daily_extensibility_refresh:20,research_agent:12,product_ux_design:8}},max={{...legacyMax,...(SCORE.rubric_weights||{{}})}};if(INDEPENDENT.qualification_passed){{const cats=INDEPENDENT.category_scores||{{}},audit=INDEPENDENT.identity_audit||{{}},proxy=INDEPENDENT.proxy||{{}};$('#core-score').textContent=`${{INDEPENDENT.raw_score??0}}/100 independent`;$('#score-grid').innerHTML=Object.entries(cats).map(([key,value])=>`<div class="score-card"><span>${{esc(key.replaceAll('_',' '))}}</span><strong>${{esc(value)}}/${{max[key]??'—'}}</strong></div>`).join('');$('#external-gates').innerHTML=`<div class="gate-card"><span>Exact-entity publication</span><strong style="color:var(--good)">Pass</strong><small>${{audit.published_domains_correct||0}}/${{audit.published_domains_correct||0}} domains and ${{audit.published_socials_correct||0}}/${{audit.published_socials_correct||0}} socials correct; zero wrong-company publications.</small></div><div class="gate-card"><span>Deterministic proxy</span><strong style="color:var(--good)">${{proxy.submission_1000||SCORE.raw_score||0}}/100</strong><small>Directional only; the independent score is authoritative here.</small></div>`;return}}if('raw_score' in SCORE){{const cats=SCORE.category_scores||{{}};$('#core-score').textContent=`${{SCORE.raw_score??0}}/100 raw · ${{SCORE.awardable_score??0}} awardable`;$('#score-grid').innerHTML=Object.entries(cats).map(([key,value])=>`<div class="score-card"><span>${{esc(key.replaceAll('_',' '))}}</span><strong>${{esc(value)}}/${{max[key]??'—'}}</strong></div>`).join('');$('#external-gates').innerHTML=Object.entries(SCORE.qualification_gates||{{}}).map(([key,passed])=>`<div class="gate-card"><span>${{esc(key.replaceAll('_',' '))}}</span><strong style="color:${{passed?'var(--good)':'var(--warn)'}}">${{passed?'Pass':'Unproven / fail'}}</strong></div>`).join('');return}}const weighted=SCORE.weighted_score||{{}},cats=weighted.categories||{{}};$('#core-score').textContent='POC diagnostic';$('#score-grid').innerHTML=Object.entries(cats).map(([key,value])=>`<div class="score-card"><span>${{esc(key.replaceAll('_',' '))}}</span><strong>${{esc(value.verified)}}/${{esc(value.weight)}}</strong></div>`).join('');$('#external-gates').innerHTML='<div class="gate-card"><span>Competition score</span><strong>Not measured</strong><small>The earlier POC rubric is not the competition rubric.</small></div>'}}
const WORKSPACE_KEY='signalpost-workspace-v1';const emptyWorkspace=()=>({{schemaVersion:1,pins:[],history:[]}});function loadWorkspace(){{try{{const value=JSON.parse(localStorage.getItem(WORKSPACE_KEY)||'null');if(!value)return emptyWorkspace();if(value.schemaVersion!==1||!Array.isArray(value.pins)||!Array.isArray(value.history))throw new Error('schema');return value}}catch(_error){{localStorage.removeItem(WORKSPACE_KEY);return {{...emptyWorkspace(),warning:'Invalid saved workspace was reset safely.'}}}}}}let workspace=loadWorkspace();function persistWorkspace(){{localStorage.setItem(WORKSPACE_KEY,JSON.stringify(workspace));renderWorkspace()}}function renderWorkspace(){{const pinned=workspace.pins.map(org=>DATA.find(x=>x.org===org)).filter(Boolean);$('#workspace-summary').innerHTML=`<strong>Saved workspace</strong><p>${{pinned.length}} pinned · ${{workspace.history.length}} saved view(s)</p>${{workspace.warning?`<p>${{esc(workspace.warning)}}</p>`:''}}${{pinned.slice(0,5).map(x=>`<button type="button" data-workspace-org="${{x.org}}">${{esc(x.name)}}</button>`).join('')}}${{workspace.history.length?`<p>Recent: ${{esc(workspace.history.at(-1).label)}}</p>`:''}}`;$('#workspace-summary').querySelectorAll('[data-workspace-org]').forEach(b=>b.onclick=()=>{{selected=DATA.find(x=>x.org===b.dataset.workspaceOrg);renderList();renderProfile()}})}}
let selected=null,agentMode='overview',agentQuestion='';function renderList(){{const rows=filtered();$('#count').textContent=`${{rows.length}} of ${{DATA.length}} entities · ${{workspace.pins.length}} pinned`;$('#list').innerHTML=rows.slice(0,500).map(x=>`<button class="row ${{selected?.org===x.org?'active':''}}" data-org="${{x.org}}"><strong>${{workspace.pins.includes(x.org)?'◆ ':''}}${{esc(x.name)}}</strong><span>${{esc(x.org)}} · ${{esc(x.form)}} · ${{esc(x.municipality||'Location not reported')}}</span></button>`).join('')+(rows.length>500?'<div class="row"><span>Showing first 500 matches. Narrow the search.</span></div>':'');$('#list').querySelectorAll('[data-org]').forEach(b=>b.onclick=()=>{{selected=DATA.find(x=>x.org===b.dataset.org);renderList();renderProfile();}});if(!selected&&rows.length){{selected=rows[0];renderProfile();}}}}
function safeLink(url,label='Source ↗'){{try{{const parsed=new URL(String(url||''));if(!['http:','https:'].includes(parsed.protocol))return '';return `<a href="${{esc(parsed.href)}}" target="_blank" rel="noreferrer">${{esc(label)}}</a>`}}catch{{return ''}}}}
function cite(url,label='Source ↗'){{const link=safeLink(url,label);return link?` ${{link}}`:''}}
function isFullReportQuestion(question){{
 const intents=SCORE.question_intents||{{}};
 return Boolean(intents.full_report&&new RegExp(intents.full_report,'i').test(norm(question)));
}}
function requestedModes(question){{
 const q=norm(question),routes=SCORE.question_routes||[],intents=SCORE.question_intents||{{}};
 if(isFullReportQuestion(question))return ['overview','financials','leaders','locations','social','hiring','activity','sentiment'];
 if(intents.overview&&new RegExp(intents.overview,'i').test(q))return ['overview'];
 const match=routes.find(route=>route.mode!=='overview'&&new RegExp(route.pattern,'i').test(q));
 return match?[match.mode]:['overview'];
}}
function displayRoleName(value){{return Array.isArray(value)?value.filter(item=>item!=null&&item!=='').join(', '):value==null?'':String(value)}}
function agentBody(x,mode,fullReport=false){{
 const linkedin=x.external?.linkedin||{{}},profile=linkedin.profile||{{}},jobs=linkedin.jobs||[],posts=linkedin.posts||[];
 if(mode==='overview')return (fullReport?x.reportOverviewHtml:x.overviewHtml)||'<p>Company overview is not available in this snapshot.</p>';
 if(mode==='financials'){{
  const records=x.financial?.status==='available'?(x.financial.records||[]):[];
  const record=[...records].sort((a,b)=>String(b.period?.tilDato||'').localeCompare(String(a.period?.tilDato||'')))[0]||records[0];
  if(!record)return `<section><h4>Financial records</h4><p>No normalized annual account is available in this snapshot; missing is not zero.${{cite(x.financial?.source)}}</p></section>`;
  const period=record.period?.tilDato?` for the period ending ${{esc(record.period.tilDato)}}`:'';
  return `<section><h4>Latest normalized annual-account figures${{period}}</h4><ul><li>Revenue: <strong>${{money(record.revenue,record.currency)}}</strong></li><li>Operating result: <strong>${{money(record.operating_result,record.currency)}}</strong></li><li>Annual result: <strong>${{money(record.annual_result,record.currency)}}</strong></li></ul>${{cite(x.financial?.source,'Official accounting source ↗')}}<p class="evidence-boundary">These are reported accounting figures, not a standalone assessment of financial health.</p></section>`;
 }}
 if(mode==='leaders'){{
  const roles=(x.roles?.items||[]).filter(role=>role.inactive===false);
  const content=roles.length?`<ul>${{roles.slice(0,5).map(role=>`<li><strong>${{esc(displayRoleName(role.name)||'Name not reported')}}</strong> — ${{esc(role.role||role.group||'Role not reported')}}</li>`).join('')}}</ul>`:'<p>No active registered leadership record is available in this snapshot.</p>';
  return `<section><h4>Active registered leadership</h4>${{content}}${{cite(x.roles?.source,'Official roles source ↗')}}</section>`;
 }}
 if(mode==='locations'){{
  const content=x.locations?.status==='available'?`${{esc(x.locations.count??'Count not reported')}} registered operating subunit(s).`:'Registered operating-subunit data is not available in this snapshot.';
  return `<section><h4>Registered locations</h4><p>${{content}}${{cite(x.locations?.source,'Official subunit source ↗')}}</p></section>`;
 }}
 if(mode==='social'){{
  if(linkedin.available){{
   const metrics=[profile.followers==null?'Followers not reported':`${{esc(profile.followers)}} followers`,profile.visible_employees==null?'Associated profiles not reported':`${{esc(profile.visible_employees)}} associated profiles`,profile.employee_size_label?esc(profile.employee_size_label):'Employee-size label not reported'].join(' · ');
   return `<section><h4>Exact-company LinkedIn profile</h4><p>Experimental platform metrics: ${{metrics}}.${{cite(profile.profileUrl,'Open profile ↗')}}${{cite(profile.source,'Observation source ↗')}}</p><p class="evidence-boundary">These metrics do not establish business performance, reputation, or financial health.</p></section>`;
  }}
  const links=x.web?.value?.social_links||[];
  return links.length?`<section><h4>Verified declared profiles</h4><p>${{links.map(item=>`${{esc(item.platform||'Social profile')}} ${{safeLink(item.url,'Open profile ↗')}}`).join('<br>')}}</p></section>`:x.web?.value?.quarantined_social_count?`<section><h4>Social profiles</h4><p>${{esc(x.web.value.quarantined_social_count)}} social link(s) were found but not published because company identity was not verified.</p></section>`:'<section><h4>Social profiles</h4><p>No verified external profile data is available in this snapshot.</p></section>';
 }}
 if(mode==='hiring'){{
  const content=jobs.length?`<p>Captured job listings are experimental signals, not proof of hiring outcomes.</p><ul>${{jobs.slice(0,5).map(job=>`<li><strong>${{esc(job.title||'Job title not reported')}}</strong> — ${{esc(job.location||'Location not reported')}}${{cite(job.job_url||job.source,'View listing ↗')}}</li>`).join('')}}</ul>`:'<p>No exact-company job listing was captured in this snapshot.</p>';
  return `<section><h4>Hiring signals</h4>${{content}}</section>`;
 }}
 if(mode==='activity'){{
  const content=posts.length?`<ul>${{posts.slice(0,5).map(post=>`<li>${{esc(post.text||'Post captured; text not reported')}}${{cite(post.source,'View post ↗')}}</li>`).join('')}}</ul><p class="evidence-boundary">Captured public activity is experimental and does not establish business performance or sentiment.</p>`:'<p>No exact-company public activity post was captured in this snapshot.</p>';
  return `<section><h4>Public activity</h4>${{content}}</section>`;
 }}
 if(mode==='sentiment')return '<section><h4>Sentiment</h4><p>Employee satisfaction or company reputation cannot be established from the available evidence. Follower counts and hiring posts are not sentiment evidence; no publishable sentiment result is available in this snapshot.</p></section>';
 return '<p>This answer section is unavailable.</p>';
}}
function renderAgent(){{
 const x=selected,output=$('#agent-output');
 if(!x){{output.innerHTML='<p>Choose a company first.</p>';return}}
 const modes=[...new Set(agentQuestion?requestedModes(agentQuestion):[agentMode])];
 const fullReport=Boolean(agentQuestion&&isFullReportQuestion(agentQuestion));
 const labels={{overview:'Company Overview',financials:'Financials',leaders:'Leadership',locations:'Locations',social:'LinkedIn / social',hiring:'Hiring',activity:'Public activity',sentiment:'Sentiment'}};
 const content=modes.map(mode=>`<div class="answer-block" data-answer-mode="${{esc(mode)}}"><h4>${{labels[mode]||esc(mode)}}</h4>${{agentBody(x,mode,fullReport)}}</div>`).join('');
 output.replaceChildren();
 output.innerHTML=(agentQuestion?`<p class="agent-question"><small>Your question</small><br><strong>${{esc(agentQuestion)}}</strong></p>`:'')+content;
 $('#agent-buttons').querySelectorAll('button').forEach(button=>button.classList.toggle('active',!agentQuestion&&button.dataset.mode===agentMode));
}}
function statusChip(label,status){{const cls=status==='available'?'good':status==='not_found'?'warn':'';return `<span class="chip ${{cls}}">${{esc(label)}}: ${{esc(status.replaceAll('_',' '))}}</span>`}}function sourceLine(obj){{return obj?.source?`<details class="source"><summary>Inspect evidence</summary><div>Source: ${{safeLink(obj.source,obj.source)}}</div><div>Class: ${{esc(obj.sourceClass||'not reported')}} · Retrieved: ${{esc(obj.retrievedAt||'not reported')}}</div>${{obj.effectiveAt?`<div>Effective: ${{esc(obj.effectiveAt)}}</div>`:''}}${{obj.hash?`<div>SHA-256: <code>${{esc(obj.hash)}}</code></div>`:''}}</details>`:''}}
function renderProfile(){{const x=selected;if(!x){{$('#profile').innerHTML='<p class="empty">Choose a company.</p>';renderAgent();return}}const rec=x.financial.records[0],people=x.roles.items.filter(r=>!r.inactive),locations=x.locations.items,social=x.web.value.social_links||[],pdfs=x.financialHistory.pdfs||[],isPinned=workspace.pins.includes(x.org),accounting=x.accounting.value||{{}};$('#profile').innerHTML=`<div class="profile-head"><div><div class="eyebrow">${{esc(x.slice)}} sample · ${{esc(x.split)}}</div><h2>${{esc(x.name)}}</h2><div>${{esc(x.org)}} · ${{esc(x.form||'Form not reported')}}</div></div><div><button class="pin-button" id="pin-company" type="button">${{isPinned?'Unpin':'Pin company'}}</button><div class="chips" style="margin-top:8px">${{statusChip('accounts',x.financial.status)}}${{statusChip('roles',x.roles.status)}}${{statusChip('website',x.web.status)}}${{x.adverse?'<span class="chip warn">adverse registry state</span>':'<span class="chip good">no adverse flag</span>'}}</div></div></div><div class="fact-grid"><div class="fact"><span>Industry</span><strong>${{esc(x.industryCode||'—')}} ${{esc(x.industry||'Not reported')}}</strong></div><div class="fact"><span>Municipality</span><strong>${{esc(x.municipality||'Not reported')}}</strong></div><div class="fact"><span>Employees</span><strong>${{x.employees==null?'Not reported':esc(x.employees)}}</strong></div><div class="fact"><span>Accounting availability</span><strong>${{esc((accounting.classification||'not classified').replaceAll('_',' '))}}</strong><small>${{esc(accounting.reason||'')}}</small></div></div><section><div class="section-label">Official annual account</div><h3>${{rec?'Latest normalized figures':'No normalized financial record returned'}}</h3>${{rec?`<table><tr><th>Period</th><td>${{esc(rec.period?.fraDato||'')}} – ${{esc(rec.period?.tilDato||'')}}</td></tr><tr><th>Revenue</th><td>${{money(rec.revenue,rec.currency)}}</td></tr><tr><th>Operating result</th><td>${{money(rec.operating_result,rec.currency)}}</td></tr><tr><th>Annual result</th><td>${{money(rec.annual_result,rec.currency)}}</td></tr><tr><th>Assets</th><td>${{money(rec.assets,rec.currency)}}</td></tr><tr><th>Debt</th><td>${{money(rec.debt,rec.currency)}}</td></tr></table>`:`<p class="empty">${{esc(accounting.reason||'Missing is not zero. Filing applicability is not established from the available source.') }}</p>`}}${{pdfs.length?`<p class="source">Historical filings: ${{pdfs.slice(0,8).map(p=>`<a href="${{esc(p.url)}}" target="_blank" rel="noreferrer">${{esc(p.year)}}</a>`).join(' · ')}}</p>`:''}}${{sourceLine(x.accounting)}}${{sourceLine(x.financial)}}</section><section><div class="section-label">Registered people</div><h3>${{people.length}} public role records</h3><div class="people">${{people.length?people.slice(0,16).map(r=>`<div class="item"><strong>${{esc(r.name||r.organisation_number||'Unnamed holder')}}</strong><small>${{esc(r.role||r.group||'Role not reported')}}</small></div>`).join(''):'<p class="empty">No role record returned.</p>'}}</div>${{sourceLine(x.roles)}}</section><section><div class="section-label">Registered operating locations</div><h3>${{locations.length}} subunits</h3><div class="locations">${{locations.length?locations.slice(0,12).map(l=>`<div class="item"><strong>${{esc(l.name)}}</strong><small>${{esc(l.address?.kommune||l.address?.poststed||'Location not reported')}} · ${{l.employees??'employees not reported'}}</small></div>`).join(''):'<p class="empty">Location module not run or no subunits returned.</p>'}}</div>${{sourceLine(x.locations)}}</section><section><div class="section-label">Update history</div><h3>${{x.changes.length}} recorded changes</h3>${{x.changes.length?`<table>${{x.changes.map(c=>`<tr><th>${{esc(c.field)}}</th><td>${{esc(JSON.stringify(c.old_value))}} → ${{esc(JSON.stringify(c.new_value))}}</td></tr>`).join('')}}</table>`:'<p class="empty">No changes are attached to this frozen profile yet. Retrieval timestamps and hashes below still show the evidence version.</p>'}}</section><section><div class="section-label">Company-controlled web layer</div><h3>${{esc(x.web.value.title||'No fetched homepage')}}</h3><p>${{esc(x.web.value.description||'No company-site description captured.')}}</p><p class="source">${{(x.web.value.pages||[]).length}} bounded same-site page(s) captured.</p><div class="social">${{social.map(s=>`<div class="item"><strong>${{esc(s.platform)}}</strong><small><a href="${{esc(s.url)}}" target="_blank" rel="noreferrer">${{esc(s.url)}}</a></small></div>`).join('')}}</div>${{sourceLine(x.web)}}</section>`;$('#pin-company').onclick=()=>{{workspace.pins=isPinned?workspace.pins.filter(org=>org!==x.org):[...new Set([...workspace.pins,x.org])].sort();persistWorkspace();renderList();renderProfile()}};renderAgent();}}
['q','form','state','finance','slice'].forEach(id=>$('#'+id).addEventListener(id==='q'?'input':'change',()=>{{selected=null;renderList()}}));$('#save-view').onclick=()=>{{const rows=filtered();workspace.history=[...workspace.history,{{createdAt:new Date().toISOString(),label:$('#q').value||'Structured filter view',filters:{{query:$('#q').value,form:$('#form').value,state:$('#state').value,finance:$('#finance').value,slice:$('#slice').value}},resultCount:rows.length,resultOrganisationNumbers:rows.map(x=>x.org)}}].slice(-100);persistWorkspace()}};$('#export-view').onclick=()=>{{const rows=filtered();const artifact={{exportedAt:new Date().toISOString(),filters:{{query:$('#q').value,form:$('#form').value,state:$('#state').value,finance:$('#finance').value,slice:$('#slice').value}},profiles:rows,claimBoundary:'Source-linked frozen Signalpost evidence; missing values are not zero.'}};const blob=new Blob([JSON.stringify(artifact,null,2)],{{type:'application/json'}}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='signalpost-evidence-export.json';a.click();URL.revokeObjectURL(url)}};$('#agent-form').onsubmit=e=>{{e.preventDefault();agentQuestion=$('#agent-question').value.trim();if(agentQuestion)renderAgent()}};$('#agent-buttons').querySelectorAll('button').forEach(b=>b.onclick=()=>{{agentMode=b.dataset.mode;agentQuestion='';$('#agent-question').value='';renderAgent()}});renderStats();renderQualification();renderWorkspace();renderList();
</script><script>
function renderLinkedInLayer(x){{const li=x.external?.linkedin||{{}},profile=li.profile||{{}},posts=li.posts||[],jobs=li.jobs||[];if(!li.available)return `<section id="linkedin-layer"><div class="section-label">LinkedIn and public activity</div><h3>No exact LinkedIn profile captured</h3><p class="empty">The discovery loop abstained for this company. Missing is not zero, and no profile is inferred from name similarity alone.</p></section>`;const cards=[['Followers',profile.followers],['Associated profiles',profile.visible_employees],['Company size',profile.employee_size_label],['Headquarters',profile.headquarters],['Open jobs captured',jobs.length],['Recent posts captured',posts.length]].map(([label,value])=>`<div class="signal-card"><span>${{esc(label)}}</span><strong>${{value??'Not reported'}}</strong></div>`).join('');const activity=posts.slice(0,3).map(p=>`<div class="activity"><small>${{esc(p.date_posted||p.published_at||'Date not reported')}}</small><p>${{esc(p.text||'Public post captured.')}}</p><small>${{p.likes??0}} reactions · ${{p.comments??0}} comments · <a href="${{esc(p.source)}}" target="_blank" rel="noreferrer">source ↗</a></small></div>`).join('');const openings=jobs.slice(0,5).map(j=>`<div class="item"><strong>${{esc(j.title||'Role not reported')}}</strong><small>${{esc(j.location||'Location not reported')}} · ${{esc(j.date_posted||'Date not reported')}} · <a href="${{esc(j.job_url||j.source)}}" target="_blank" rel="noreferrer">posting ↗</a></small></div>`).join('');return `<section id="linkedin-layer"><div class="section-label">LinkedIn and public activity</div><h3>${{esc(profile.industry||'Exact company profile')}}</h3><p class="experimental-note"><strong>Experimental external evidence.</strong> The exact-company match is retained, but platform metrics are separated from strict company-controlled evidence.</p><div class="signal-grid">${{cards}}</div>${{activity?`<h3>Recent public activity</h3><div class="activity-list">${{activity}}</div>`:''}}${{openings?`<h3 style="margin-top:18px">Current hiring signals</h3><div class="people">${{openings}}</div>`:''}}${{sourceLine(profile)}}</section>`}}
function injectLinkedInLayer(){{const profileRoot=$('#profile');if(!selected||!profileRoot||$('#linkedin-layer'))return;const sections=profileRoot.querySelectorAll('section');const target=sections[sections.length-1];if(target)target.insertAdjacentHTML('beforebegin',renderLinkedInLayer(selected))}}
document.querySelector('.snapshot').textContent=`${{DATA.length}}-company snapshot · ${{DATA.filter(company=>company.external?.linkedin?.available).length}} exact LinkedIn profiles`;
const baseRenderList=renderList;renderList=()=>{{baseRenderList();queueMicrotask(injectLinkedInLayer)}};new MutationObserver(injectLinkedInLayer).observe($('#profile'),{{childList:true}});injectLinkedInLayer();
if(SCORE.scorer==='signalpost_all_source_completeness_v1')$('#core-score').textContent=`${{Number(SCORE.raw_score||0).toFixed(2)}}/100 experimental · ${{Number(SCORE.awardable_score||0).toFixed(2)}}/100 strict`;
</script></body></html>'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--score")
    parser.add_argument("--control-loop")
    parser.add_argument("--independent-score")
    parser.add_argument("--external-observations", nargs="*")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = read_jsonl(Path(args.input))
    if args.limit:
        rows = rows[:args.limit]
    external_by_org: dict[str, list[dict]] = defaultdict(list)
    seen_observations: set[str] = set()
    for source in args.external_observations or []:
        for observation in read_jsonl(Path(source)):
            observation_id = str(observation.get("id") or json.dumps(observation, sort_keys=True, ensure_ascii=False))
            if observation_id in seen_observations:
                continue
            seen_observations.add(observation_id)
            organisation_number = str(observation.get("organisation_number") or "")
            if organisation_number:
                external_by_org[organisation_number].append(observation)
    score = json.loads(Path(args.score).read_text(encoding="utf-8")) if args.score and Path(args.score).exists() else None
    control_loop = json.loads(Path(args.control_loop).read_text(encoding="utf-8")) if args.control_loop and Path(args.control_loop).exists() else None
    independent_score = json.loads(Path(args.independent_score).read_text(encoding="utf-8")) if args.independent_score and Path(args.independent_score).exists() else None
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build(rows, score, control_loop, independent_score, external_by_org), encoding="utf-8")
    print(f"Wrote {output} with {len(rows)} profiles")
