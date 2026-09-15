"""Runner executable entrypoint.

The concrete LLM-backed AgentProgram is intentionally not composed here yet. The runner infrastructure
is independent of the API and becomes executable once the challenge-1 data-analyst program is supplied.
"""


def main() -> None:
    raise RuntimeError(
        "Runner foundation is configured, but no AgentProgram implementation has been wired yet."
    )


if __name__ == "__main__":
    main()
