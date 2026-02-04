# Title
KSA Hospital Bed Occupancy Forecasting: Prophet + LSTM hybrid pipeline

# Category
project

# Problem
Hospitals need reliable short-horizon capacity forecasts at ward level to support operational decision-making. Raw exports and calendar effects make forecasting messy, and models must be maintainable and runnable on constrained infrastructure.

# My role
I delivered a per-ward forecasting system for Kantonsspital Aarau (KSA) that operationalizes data preparation, training, validation, and calibration in a repeatable pipeline. I focused on aligning modeling choices with practical operational constraints and measurable validation metrics.

# What I built
I built a 7-stage pipeline that ingests hospital exports and regional calendars, constructs per-ward daily time series, trains hybrid models (Prophet for admissions, LSTM for discharges), and produces a 7-day forecast with validation and alert thresholds. The system includes an auto-calibration engine that can adjust post-processing parameters without retraining when appropriate.

# Scale and impact
The system produces ward- and hospital-level forecasts tuned for operational use, with weekly validation using MAE, RMSE, MAPE, and bias metrics. It is designed for fast daily production runs on a single hospital server and supports scheduled execution for ongoing use.

# Tech stack
Pipeline/orchestration: Python 3.8 CLI with modular scripts and orchestration via command-line flags. Modeling: Prophet, TensorFlow/Keras LSTM, conservation-based dynamics, ward-specific configuration. Validation/calibration: metric reporting and guardrails based on variance/percentiles, seasonal and holiday patterns.

# Key decisions and trade-offs
I used a hybrid modeling approach to match different processes (admissions vs discharges), trading single-model simplicity for better fit to operational realities. Auto-calibration was preferred to frequent retraining to reduce operational burden and speed up iteration. The CLI-driven pipeline favors transparency and reproducibility over an early move to heavier orchestration platforms.

# Links
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf

