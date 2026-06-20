# Diagnosis fixtures (forward-compatible shape)

`cases.json` covers the **retrieval half** of the "Explain this error" flow
(does the engine chunk that explains an error surface?). It is graded by
`harness.score_case`.

The **diagnosis half** - is the agent's actual root cause + fix correct? -
is future work (an LLM-judge, fed by answer feedback). Diagnosis fixtures
will use this shape so they drop in without reshaping existing cases:

    {
      "id": "subclass-not-detected",
      "error_text": "<pasted console error>",
      "failing_code": "<the user's import snippet>",
      "edition": "2014",
      "retrieval_target": { "source_substring": "Functions1" },
      "rubric": {
        "root_cause_file_line": "Functions1.js:1709",
        "must_mention": ["subclass not detected", "subclassGainedLevel"],
        "fix_checks": ["uses var", "calls AddSubClass", "valid regExpSearch"]
      }
    }

- `retrieval_target` reuses the `cases.json` `expect` schema.
- `rubric` is the future judge's grading contract.
- Fixtures are seeded by dogfooding and grown via the answer-feedback loop.
