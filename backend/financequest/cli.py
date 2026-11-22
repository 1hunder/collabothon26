import json
from pathlib import Path
from typing import Annotated

import typer
from alembic import command
from alembic.config import Config

from financequest.config import get_settings

FIXTURES = Path(__file__).parent / "fixtures"

app = typer.Typer(no_args_is_help=True)
db_app = typer.Typer(no_args_is_help=True)
app.add_typer(db_app, name="db")
refpack_app = typer.Typer(no_args_is_help=True)
app.add_typer(refpack_app, name="refpack")
prices_app = typer.Typer(no_args_is_help=True)
app.add_typer(prices_app, name="prices")
check_app = typer.Typer(no_args_is_help=True)
app.add_typer(check_app, name="check")
report_app = typer.Typer(no_args_is_help=True)
app.add_typer(report_app, name="report")
fixtures_app = typer.Typer(no_args_is_help=True)
app.add_typer(fixtures_app, name="fixtures")


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Run Alembic upgrade."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    command.upgrade(cfg, revision)


@refpack_app.command("import")
def refpack_import(
    case_md: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    prices_csv: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    out: Annotated[Path, typer.Option("--out", help="Output directory for draft and report")],
) -> None:
    """Draft a campaign manifest from a reference pack and write a validation report."""
    from financequest.refpack.importer import import_pack

    fake = None
    if get_settings().fake_llm:
        fixture = FIXTURES / "reference" / "fq-av-001" / "manifest.json"
        fake = [json.loads(fixture.read_text(encoding="utf-8"))]
    result = import_pack(case_md, prices_csv, out, fake)
    typer.echo(f"draft:  {result.manifest_path}")
    typer.echo(f"report: {result.report_path}")
    typer.echo(f"errors: {len(result.report.errors)}  warnings: {len(result.report.warnings)}")
    if not result.report.ok:
        raise typer.Exit(1)


@refpack_app.command("approve")
def refpack_approve(
    pack_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    salt: Annotated[int, typer.Option("--salt", help="Run salt added to the case seed")] = 0,
) -> None:
    """Disguise a reviewed pack, run the final scan and store it as a playable scenario."""
    from sqlmodel import Session

    from financequest.db.session import get_engine
    from financequest.refpack.approve import approve_pack

    with Session(get_engine()) as session:
        res = approve_pack(pack_dir, session, salt)
    if res.ok:
        typer.echo(f"scenario {res.scenario_id} status={res.status} salt={res.salt}")
        return
    typer.echo("NOT PLAYABLE:")
    for r in res.reasons:
        typer.echo(f"- {r}")
    raise typer.Exit(1)


@refpack_app.command("seed")
def refpack_seed(
    root: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="One pack per sub-folder")
    ] = Path(__file__).parent / "fixtures" / "reference",
) -> None:
    """Approve every curated pack under ROOT (idempotent). Run on every deploy: these are the
    Guild notices every player sees on the Quest Board."""
    from sqlmodel import Session

    from financequest.db.session import get_engine
    from financequest.refpack.approve import approve_pack

    failed = 0
    for pack_dir in sorted(p for p in root.iterdir() if (p / "manifest.json").exists()):
        with Session(get_engine()) as session:
            res = approve_pack(pack_dir, session, 0)
        if res.ok:
            typer.echo(f"{pack_dir.name}: scenario {res.scenario_id} status={res.status}")
        else:
            failed += 1
            typer.echo(f"{pack_dir.name}: NOT PLAYABLE: " + "; ".join(res.reasons[:5]), err=True)
    if failed:
        raise typer.Exit(1)


@app.command("intake")
def intake(
    md: Annotated[Path, typer.Option("--md", exists=True, dir_okay=False)],
    extra: Annotated[Path | None, typer.Option("--extra", exists=True, dir_okay=False)] = None,
    spotcheck: Annotated[Path, typer.Option("--spotcheck")] = Path("intake_spotcheck.csv"),
    dry_run_fake_llm: Annotated[bool, typer.Option("--dry-run-fake-llm")] = False,
) -> None:
    """Extract, validate and tag cases; write intake_spotcheck.csv for the team."""
    from sqlmodel import Session

    from financequest.db.session import get_engine
    from financequest.llm import get_node_llm
    from financequest.pipeline.intake import (
        FixtureIntakeLLM,
        persist_results,
        read_results,
        write_spotcheck,
    )

    with Session(get_engine()) as session:
        for path, origin in ((md, "md61"), (extra, "extra")):
            if path is None:
                continue
            llm = FixtureIntakeLLM.for_md(path) if dry_run_fake_llm else get_node_llm()
            summ = persist_results(session, read_results(path, llm), origin)
            typer.echo(
                f"{path.name}: ok={summ.ok} untagged={summ.untagged} "
                f"skipped={summ.skipped} errors={summ.errors}"
            )
        n = write_spotcheck(session, spotcheck)
    typer.echo(f"spot-check: {spotcheck} ({n} cases)")


@prices_app.command("fetch")
def prices_fetch(
    case: Annotated[str | None, typer.Option("--case")] = None,
    all_: Annotated[bool, typer.Option("--all")] = False,
) -> None:
    """yfinance -> Parquet cache (CACHE_DIR), gap flags, beat prices."""
    from sqlmodel import Session, select

    from financequest.db.models import SourceCase
    from financequest.db.session import get_engine
    from financequest.pipeline.prices import fetch_case_prices

    if not case and not all_:
        raise typer.BadParameter("pass --case ID or --all")
    with Session(get_engine()) as session:
        ids = [case] if case else list(session.exec(select(SourceCase.id)).all())
        for cid in ids:
            res = fetch_case_prices(session, cid, Path(get_settings().cache_dir))
            row = session.get(SourceCase, cid)
            state = (
                "no prices" if res is None else f"{res.n_points} points, {len(res.gap_flags)} gaps"
            )
            typer.echo(f"{cid}: {state} [{row.status if row else '?'}]")


@check_app.command("run")
def check_run(
    label: Annotated[str, typer.Option("--label")],
    cases: Annotated[str, typer.Option("--cases", help="all or comma-separated ids")] = "all",
    concurrency: Annotated[int | None, typer.Option("--concurrency")] = None,
    dry_run_fake_llm: Annotated[bool, typer.Option("--dry-run-fake-llm")] = False,
) -> None:
    """Run the gate over the batch; an unfinished run with the same label is resumed."""
    import asyncio

    from sqlmodel import Session

    from financequest.db.session import get_engine
    from financequest.reid.batch import (
        dry_run_llm_factory,
        live_llm_factory,
        run_batch,
        start_run,
    )

    factory = dry_run_llm_factory if dry_run_fake_llm else live_llm_factory
    ids = None if cases == "all" else [c.strip() for c in cases.split(",") if c.strip()]
    with Session(get_engine()) as session:
        run = start_run(session, label, get_settings())
        run_id = run.id
    assert run_id is not None
    summary = asyncio.run(
        run_batch(
            lambda: Session(get_engine()),
            run_id,
            ids,
            llm_factory=factory,
            concurrency=concurrency,
            on_case_done=lambda cid, status: typer.echo(f"{cid}: {status}"),
        )
    )
    typer.echo(f"run {run_id} finished; skipped already-done: {len(summary.already_done)}")


@report_app.command("build")
def report_build(
    run: Annotated[int, typer.Option("--run")],
    out: Annotated[Path, typer.Option("--out")] = Path("report.html"),
) -> None:
    """HTML and JSON report for one run."""
    from sqlmodel import Session

    from financequest.db.session import get_engine
    from financequest.report.render import build_report_data, write_report

    with Session(get_engine()) as session:
        data = build_report_data(session, run)
        html, js = write_report(session, run, out)
    typer.echo(data["header"])
    typer.echo(f"wrote {html} and {js}")


@fixtures_app.command("export")
def fixtures_export(
    approved: Annotated[bool, typer.Option("--approved")] = True,
    out: Annotated[Path, typer.Option("--out")] = Path(__file__).parent / "fixtures" / "scenarios",
) -> None:
    """Versioned JSON of approved scenarios plus their secrets."""
    from sqlmodel import Session

    from financequest.db.session import get_engine
    from financequest.pipeline.export import export_approved

    with Session(get_engine()) as session:
        paths = export_approved(session, out)
    typer.echo(f"exported {len(paths)} scenarios to {out}")


@fixtures_app.command("import")
def fixtures_import(
    src: Annotated[Path, typer.Option("--src")] = Path(__file__).parent / "fixtures" / "scenarios",
) -> None:
    """Load exported scenarios into scenario/scenario_secret (source=gate)."""
    from sqlmodel import Session

    from financequest.db.session import get_engine
    from financequest.pipeline.export import import_fixtures

    with Session(get_engine()) as session:
        n = import_fixtures(session, src)
    typer.echo(f"imported {n} scenarios from {src}")


quest_app = typer.Typer(no_args_is_help=True)
app.add_typer(quest_app, name="quest")


@quest_app.command("generate")
def quest_generate(
    category: Annotated[str | None, typer.Option(help="Spending category, e.g. music")] = None,
    ticker: Annotated[str | None, typer.Option(help="Company ticker inside the category")] = None,
) -> None:
    """Generate one personal quest now, in the foreground (e.g. the pre-created demo quest)."""
    from datetime import date

    from sqlmodel import Session

    from financequest.db.models import PlayerSession
    from financequest.db.models_personal import GenerationJob
    from financequest.db.session import get_engine
    from financequest.personal import jobs
    from financequest.personal import transactions as tx

    with Session(get_engine()) as s:
        player = PlayerSession()
        s.add(player)
        s.commit()
        if category:
            cat = tx.CATEGORIES[category]
            comp = next((c for c in cat.companies if c.ticker == ticker), cat.companies[0])
            job = GenerationJob(session_id=player.id, kind="extra", quest_date=date.today(),
                                category=cat.key, category_label=cat.label, company=comp.name,
                                ticker=comp.ticker)  # fmt: skip
            s.add(job)
            s.flush()
            job.pack_dir = jobs.quest_prefix(job.id)
            s.add(job)
            s.commit()
        else:
            job = jobs._new_job(s, player.id, "extra", date.today())  # noqa: SLF001
        job_id, company = job.id, f"{job.company} ({job.ticker})"
    typer.echo(f"generating a quest for {company} ...")
    jobs.run_job(job_id)
    with Session(get_engine()) as s:
        done = s.get(GenerationJob, job_id)
        assert done is not None
        typer.echo(f"status={done.status} scenario={done.scenario_id} error={done.error or '-'}")
        if done.status != "ready":
            raise typer.Exit(1)


if __name__ == "__main__":
    app()


veteran_app = typer.Typer(no_args_is_help=True)
app.add_typer(veteran_app, name="veteran")


@veteran_app.command("demo-hero")
def veteran_demo_hero(
    name: Annotated[str, typer.Option(help="The demo hero's name")] = "Tarn",
    scenario: Annotated[
        list[str] | None,
        typer.Option(help="Scenario id to play (repeat for several); default: different companies"),
    ] = None,
    campaigns: Annotated[int, typer.Option(min=1, max=6)] = 3,
) -> None:
    """Create a demo session whose hero has finished campaigns, for the Veteran. Runs on the
    scripted agents: no keys, no network. Prints the session id to open the app with."""
    import os
    import uuid

    os.environ["FAKE_LLM"] = "1"  # scripted agents and placeholder art while seeding
    os.environ.pop("GOOGLE_GENAI_API_KEY", None)
    get_settings.cache_clear()
    from financequest.veteran.demo import seed_demo_hero

    ids = [uuid.UUID(s) for s in scenario] if scenario else None
    out = seed_demo_hero(name=name, scenario_ids=ids, campaigns=campaigns)
    typer.echo(f"session_id: {out['session_id']}")
    n, companies = len(out["campaigns"]), out["distinct_companies"]
    typer.echo(f"finished campaigns: {n} on {companies} companies")
    if out["distinct_companies"] < 2:
        typer.echo(
            "note: every campaign is on the same company. While a new campaign on that company "
            "runs, the Veteran keeps the old ones sealed. Import or generate other quests and pass "
            "--scenario to play different companies."
        )
    typer.echo(f"open the app with ?session={out['session_id']}")


@veteran_app.command("rebuild")
def veteran_rebuild() -> None:
    """Throw away and rebuild the Veteran's memory of every hero from the campaign tables."""
    from sqlmodel import Session, select

    from financequest.db.models_campaign import Hero
    from financequest.db.session import get_engine
    from financequest.veteran import memory

    with Session(get_engine()) as db:
        heroes = list(db.exec(select(Hero)))
        n = 0
        for hero in heroes:
            n += len(memory.rebuild(db, hero.id))
        db.commit()
    typer.echo(f"rebuilt {n} campaign memories for {len(heroes)} heroes")
