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

## Final System Features

### Sensing

* Bean temperature sensing
* Real-time temperature monitoring
* Temperature profile tracking

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

### Camera Monitoring and Data Processing

* Roast data logging
* Raspberry Pi camera integration
* Real-time bean colour monitoring using grayscale analysis

### Future Development

* AI-assisted roast optimisation
* Roast profile recommendations
* Computer vision techniques for roast classification

---

## Hardware Overview

The final prototype consisted of:

* Raspberry Pi 4
* Modified hot-air popcorn popper
* K-type thermocouple
* MAX31855 thermocouple interface
* Solid State Relay (SSR)
* Custom PETG 3D-printed fan
* Heater assembly
* Cooling fan system
* Raspberry Pi camera
* Raspberry Pi display
* Protective enclosures and cable management hardware

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

## Project Outcome

The project successfully delivered a fully functional smart coffee roaster capable of automated temperature-controlled roasting, cooling, and camera-assisted roast monitoring.

Multiple successful roasting trials were completed throughout the development of this project.

The final system demonstrated the integration of embedded systems, control engineering, computer vision, and software development within a practical coffee roasting application.

---

## Design Decisions

### Fluidised Bed Roasting

A popcorn popper platform was selected as a low-cost fluidised bed roasting solution suitable for rapid prototyping.

### Custom Fan Design

A custom PETG 3D-printed fan was developed to improve airflow and bean circulation within the roasting chamber.

### MPC Control

Initial PID control testing revealed temperature overshoot. Therefore, the project transitioned from PID control to Model Predictive Control (MPC) after testing showed improved temperature regulation and reduced overshoot.

### Bean Temperature Monitoring

The final system used bean temperature as the primary process variable for monitoring roast progress and controlling the roasting process.

### Preheat Functionality

The roasting process includes a preheating stage. The chamber is first heated before beans are added. The system detects the temperature drop caused by introducing the beans and then automatically transitions into the normal roasting process.

This approach allows the roast profile to more closely resemble the thermal behaviour of larger commercial coffee roasters.

---

## Project Updates

* [Progress Update – 7th May 2026](blog/progress-update-7th-may.md)
* [Progress Update – 21st May 2026](blog/progress-update-21st-may.md)
* [Progress Update – 7th June 2026](blog/progress-update-7th-june.md)

## Disclaimer

This project involves experimentation with heating systems and mains-powered devices. Appropriate electrical and thermal safety precautions must always be followed.
