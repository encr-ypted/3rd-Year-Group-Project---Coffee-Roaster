# 3rd-Year-Group-Project---Coffee-Roaster

# Smart Coffee Roaster

## Overview

This project focuses on developing an AI-enabled small batch coffee roasting machine aimed at improving sustainability, accessibility, and roast consistency.

The system is based on a modified fluidised bed coffee roaster using a hot-air popcorn popper as the initial platform. The project combines embedded systems, sensing, control engineering, and AI technologies to create a low-cost intelligent roasting solution.

---

## Project Goals

* Develop a safe and controllable small-batch coffee roaster
* Improve roast consistency using sensing and closed-loop control
* Explore AI-assisted roast optimisation
* Reduce waste caused by inconsistent roasting
* Create an accessible and low-cost roasting platform

---

## Current System Features

### Sensing

* Bean temperature sensing
* Air temperature sensing
* Real-time temperature monitoring

### Control

* Heater control
* Fan speed control
* Roast profile execution
* Cooling functionality
* Emergency stop functionality

### User Interface

* Local web-based interface
* Real-time temperature graphing
* Roast profile presets
* Start Roast functionality
* Stop & Cool functionality
* Emergency Stop functionality

### AI / Future Development

* Roast data logging
* Camera-based bean colour monitoring
* AI-assisted roast optimisation
* Roast profile recommendations

---

## Technologies Used

* Raspberry Pi 4
* Embedded systems
* Temperature sensing
* Solid State Relay (SSR) control
* Control systems (PID and MPC)
* Python
* Web-based user interfaces
* Data logging
* Power electronics

---

## Team Members

- Tayo Babs-Olugbemi
- Sami Marouf
- Rojan Ragunathan
- Patanwit Sawatyanon
- Yikai Su
- Peter Z Wang

---

## Sustainability Focus

This project aims to improve sustainability in coffee roasting by:

* Reducing roasting waste
* Improving roast repeatability
* Supporting small-batch roasting
* Exploring energy-efficient control methods
* Increasing accessibility to roasting technology

---

## Current Project Status

The project has successfully achieved a working prototype capable of:

* Roasting coffee beans
* Monitoring roast temperature in real time
* Controlling heater output
* Controlling airflow
* Executing roast profiles
* Performing controlled cooling
* Providing user interaction through a graphical interface

Multiple successful roast tests have been completed.

Current development is focused on enclosure improvements, display integration, and future AI-assisted roasting features.

---

## Design Decisions

### Fluidised Bed Roasting

A popcorn popper platform was selected as a low-cost fluidised bed roasting solution suitable for rapid prototyping.

### Custom Fan Design

A custom PETG 3D-printed fan was developed to improve airflow and bean circulation within the roasting chamber.

### MPC Control

Initial PID control testing revealed temperature overshoot. The project has since transitioned towards Model Predictive Control (MPC) to improve temperature regulation performance.

### Dual Temperature Monitoring

Future development includes the use of separate bean and air temperature measurements to improve roast monitoring and control performance.

---

## Project Updates

* [Progress Update – 7th May 2026](blog/progress-update-7th-may.md)
* [Progress Update – 21st May 2026](blog/progress-update-21st-may.md)
* [Progress Update – 7th June 2026](blog/progress-update-7th-june.md)

Future updates will be added here throughout the project lifecycle.

---

## Disclaimer

This project involves experimentation with heating systems and mains-powered devices. Appropriate electrical and thermal safety precautions must always be followed.
