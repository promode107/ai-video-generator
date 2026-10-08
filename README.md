# Automated AI Video Generator

An automated video generation system developed as part of my internship at **Hello Alfred**.

The project is designed to convert structured content into generated videos by combining AI-generated narration, speech synthesis, media processing, and cloud-based storage and execution.

## About the Project

The Internship Video Generator automates the video creation workflow from content input to a final rendered video.

The system performs the following major steps:

1. Accepts and processes structured content.
2. Generates or prepares the required video scenes.
3. Converts generated text into speech.
4. Processes audio and visual components using FFmpeg.
5. Combines the generated components into a final video.
6. Stores and processes files using Azure cloud services.
7. Produces the final video output for further use.

## Key Features

- Automated video generation pipeline
- AI-assisted content processing
- Text-to-speech narration
- Scene-based video generation
- Automated audio/video processing
- FFmpeg-based media composition
- Azure cloud integration
- Modular and extensible architecture
- Automated workflow orchestration

## Technology Stack

### Programming
- Python

### Cloud & AI
- Microsoft Azure
- Azure OpenAI
- Azure AI Speech
- Azure Blob Storage
- Azure Functions

### Media Processing
- FFmpeg

### Development
- Python virtual environment
- JSON-based configuration
- Git / GitHub

## Project Architecture

```text
Input Content
      │
      ▼
Content Processing
      │
      ▼
Scene Generation
      │
      ├──────────────► Text-to-Speech
      │                     │
      │                     ▼
      │                  Audio
      │
      ▼
Visual / Scene Assets
      │
      ▼
FFmpeg Video Processing
      │
      ▼
Final Video
      │
      ▼
Azure Storage / Output
```

## Repository Structure

```text
internship-video-generator/
│
├── README.md
├── .gitignore
├── local.settings.json.example
├── requirements.txt
│
├── src/
│   └── ...
│
├── functions/
│   └── ...
│
└── ...
```

> The exact structure may vary depending on the deployment and development environment.

## Configuration

This project uses environment-based configuration for cloud services and API credentials.

For local development, copy:

```text
local.settings.json.example
```

to:

```text
local.settings.json
```

and provide your own credentials.

**Never commit real API keys, access tokens, passwords, connection strings, or other secrets to GitHub.**

The repository intentionally contains only placeholder configuration values.

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR-USERNAME/internship-video-generator.git
cd internship-video-generator
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the required environment variables or local settings using the example configuration file.

Make sure **FFmpeg** is installed and available in the system PATH.

## Running the Project

After configuring the required services and dependencies, run the relevant application or Azure Functions entry point according to the project configuration.

Refer to the source files and configuration examples for the appropriate local execution workflow.

## Security

This public repository does **not** contain production credentials or private access information.

All secrets should be supplied through:

- Environment variables
- Local configuration files
- Azure configuration
- Secret-management mechanisms

Do not commit:

```text
local.settings.json
.env
API keys
Access tokens
Connection strings
Passwords
Private certificates
```

## Internship Context

This project was developed as part of my **internship at Hello Alfred**, where I worked on automation and AI-assisted video generation workflows.

The project provided practical experience with:

- Cloud-based application development
- AI service integration
- Automated media processing
- Serverless workflows
- API-based architectures
- Azure services
- Software development and deployment practices

## Disclaimer

This repository contains a sanitized version intended for portfolio and demonstration purposes.

Company-specific credentials, private configurations, proprietary assets, and other confidential information have been excluded.

