# Huawei Cup Mathematical Modeling Skill

> An open-source AI Agent Skill for mathematical modeling competitions, with a primary focus on the Huawei Cup / China Postgraduate Mathematical Contest in Modeling.

一个面向数学建模竞赛的开源 AI Agent Skill，主要针对 **华为杯 / 中国研究生数学建模竞赛**，提供从赛题分析、模型选择、建模实现、结果验证到论文审查的结构化工作流。

---

## Overview

Mathematical modeling competitions require more than selecting an algorithm.

A complete solution usually involves:

* understanding the problem correctly;
* identifying variables, assumptions, and constraints;
* comparing multiple modeling approaches;
* implementing and validating the selected model;
* checking the consistency of equations, code, figures, and conclusions;
* organizing the final paper into a reproducible and defensible solution.

This repository provides an AI-agent-oriented workflow for these tasks.

The project is designed primarily for the **Huawei Cup**, while many of its modeling workflows can also be adapted to other university-level mathematical modeling competitions.

---

## Features

* Structured competition problem analysis
* Variable and constraint identification
* Mathematical modeling strategy generation
* Model selection and comparison
* Python implementation assistance
* Data-analysis workflow guidance
* Model validation and error checking
* Sensitivity and robustness analysis guidance
* Mathematical modeling paper review
* Equation / code / result consistency checking
* Reproducible modeling workflow
* Traceability and review templates

---

## Project Structure

```text
huawei-cup-modeling-skill/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── SKILL.md
├── scripts/
├── references/
├── templates/
└── rules/
```

### Main Components

**`SKILL.md`**

The main entry point of the Agent Skill. It defines the modeling workflow, execution stages, review requirements, and agent behavior.

**`scripts/`**

Supporting scripts for workflow execution, validation, state management, or other automated tasks.

**`references/`**

Reference material used during problem analysis, modeling, validation, and research.

**`templates/`**

Reusable templates for modeling tasks, review procedures, traceability, and structured outputs.

**`rules/`**

Rules and constraints for mathematical modeling, validation, writing, and workflow execution.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/ruoxuanli0120-lab/huawei-cup-modeling-skill.git
```

Enter the repository:

```bash
cd huawei-cup-modeling-skill
```

The main Agent Skill instructions are located in:

```text
SKILL.md
```

An AI coding or reasoning agent that can read repository instructions can use `SKILL.md` as the primary workflow entry point.

---

## Usage

The Skill is intended to guide an AI agent through a structured mathematical modeling workflow.

A typical request might be:

> Analyze this mathematical modeling problem. Identify the key objectives, variables, assumptions, and constraints. Compare suitable modeling approaches, select an appropriate method, implement and validate the model, and check whether the final equations, code, figures, results, and conclusions are consistent.

The agent should then follow the workflow defined in `SKILL.md` and use the supporting resources in this repository when necessary.

---

## Typical Workflow

```text
Competition Problem
        ↓
Problem Understanding
        ↓
Objective / Variable / Constraint Analysis
        ↓
Candidate Model Comparison
        ↓
Model Formulation
        ↓
Implementation
        ↓
Validation & Sensitivity Analysis
        ↓
Visualization & Result Interpretation
        ↓
Paper Review
        ↓
Consistency / Reproducibility Check
```

The goal is not only to obtain a numerical result, but to produce a modeling process that is explainable, reproducible, and technically defensible.

---

## Example Use Cases

### Problem Analysis

Use the Skill to identify:

* the main objective of each subproblem;
* decision variables and dependent variables;
* explicit and implicit constraints;
* available data and missing information;
* assumptions that need to be justified.

### Model Selection

The workflow can help compare candidate approaches according to:

* problem structure;
* available data;
* interpretability;
* computational complexity;
* assumptions;
* validation requirements.

### Model Validation

The Skill emphasizes checking whether a model is actually supported by evidence.

Typical checks may include:

* residual analysis;
* error metrics;
* sensitivity analysis;
* robustness analysis;
* baseline comparison;
* constraint verification;
* consistency between code and equations.

### Paper Review

The workflow can also be used before submission to examine whether:

* notation is consistent;
* equations match the implementation;
* tables and figures match the reported results;
* conclusions are supported by the model;
* important assumptions and limitations are disclosed.

---

## Competition Scope

The project currently focuses primarily on:

* Huawei Cup / China Postgraduate Mathematical Contest in Modeling

The underlying modeling workflow may also be useful for:

* CUMCM
* MCM / ICM
* other university-level mathematical modeling competitions

Support for competitions other than the Huawei Cup should be treated as an area for continued testing and improvement.

---

## Design Goals

This project focuses on five principles.

### Reproducibility

Important modeling steps should be reproducible instead of depending only on an AI-generated conclusion.

### Validation

A model should be tested, not merely produced.

### Traceability

Important conclusions should be traceable to assumptions, equations, data, code, or validation evidence.

### Consistency

Equations, code, figures, tables, and written conclusions should describe the same model and results.

### Human Review

The Skill is intended to assist modeling and review rather than replace human judgment. Users remain responsible for checking the final model, code, results, and competition requirements.

---

## Current Release

### v0.1.0 — Initial Public Release

The initial public release establishes the core repository structure and mathematical modeling workflow, including:

* main Agent Skill instructions;
* modeling references;
* workflow and validation scripts;
* reusable templates;
* modeling and writing rules;
* contribution guidelines.

Future releases will improve the workflow based on testing, issues, and community feedback.

---

## Roadmap

Planned areas of development include:

* [ ] More reproducible modeling examples
* [ ] Additional model-selection guidance
* [ ] More automated validation tools
* [ ] Additional sensitivity-analysis workflows
* [ ] Improved paper consistency checking
* [ ] Example Huawei Cup workflows
* [ ] Additional documentation
* [ ] Improved support for other mathematical modeling competitions
* [ ] More automated tests for scripts and workflow rules

---

## Contributing

Contributions are welcome.

You can contribute by:

* reporting bugs;
* opening Issues;
* improving documentation;
* suggesting modeling methods;
* improving existing rules or templates;
* adding validation tools;
* submitting Pull Requests;
* providing reproducible mathematical modeling examples.

Please read [`CONTRIBUTING.md`](./CONTRIBUTING.md) before submitting a Pull Request.

---

## Feedback

Real-world testing is important for improving this project.

If you use the Skill and discover:

* incorrect modeling recommendations;
* unclear instructions;
* broken scripts;
* missing validation steps;
* unnecessary workflow steps;
* useful new modeling scenarios;

please open a GitHub Issue.

Feedback supported by reproducible examples is especially valuable.

---

## License

This project is released under the **MIT License**.

See [`LICENSE`](./LICENSE) for details.

---

## Maintainer

Maintained by **ruoxuanli0120-lab**.

Project:

`huawei-cup-modeling-skill`

---

## Disclaimer

This project is an open-source modeling and research workflow tool.

It does not guarantee competition results, awards, or correctness of generated models. Users should independently verify mathematical assumptions, implementations, experimental results, references, and the official rules of the competition they participate in.
