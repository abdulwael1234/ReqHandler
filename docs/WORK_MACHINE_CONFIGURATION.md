# Work-Machine Configuration Checklist

This repository copy intentionally contains no real work documents, identifiers,
paths, templates, AUTOSAR configuration, or proprietary compatibility rules.
Complete this checklist only after transferring the full repository to the work
computer. Do not copy the completed values back to the external-development
environment.

## Required before real-data operation

- Obtain and record the SRS-015 security/stakeholder authorization governing
  whether any real requirement text may be sent to Gemini. Without approval,
  keep the system in synthetic-data-only mode even on the work computer.
- Define supported source input formats and source-input adapters.
- Define source identifiers and their mapping to `source_reference`.
- Install the exact R210 output templates and select the output file format.
- Define file and artifact naming conventions and output paths.
- Define AUTOSAR package paths and metamodel/version identifiers.
- Define the `access_point` selection rule for DataReadAccess,
  DataWriteAccess, and ServerCallPoint (SRS-064).
- Define and validate port-interface compatibility rules (SRS-071).

## Verification before enabling work-specific generation

- Validate every value above against representative real data locally.
- Confirm generated files match the approved work templates byte-for-byte where
  determinism is required.
- Confirm Gemini-facing projections contain only the fields allowed by SRS-015a.
- Confirm no real work data, completed configuration, generated output, or review
  report is committed or transferred back outside the work computer.

Until this checklist is complete, use synthetic fixtures and keep work-specific
generation disabled. The SRS-125 fallback shall accept an interface connection
whose compatibility cannot yet be verified, but it must create an `incomplete`
review issue.
