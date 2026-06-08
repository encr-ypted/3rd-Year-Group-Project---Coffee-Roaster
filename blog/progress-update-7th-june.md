# Smart Coffee Roaster – Progress Update
## 7 June 2026

---

# Introduction

Since the previous update, the project has progressed from early prototyping into a fully functional smart coffee roasting system.

The team has focused on integrating the core hardware, control system, and user interface required to perform automated coffee roasting. Multiple successful roasting tests have now been completed, allowing the team to evaluate system performance and begin refining the overall design.

The current system is capable of monitoring roast temperature, controlling airflow and heating, and executing roasting profiles through a dedicated user interface.

---

# Hardware Integration and Testing

Since the previous update, all ordered components have been received and integrated into the prototype system.

The team has successfully tested:

* Raspberry Pi 4 integration
* K-type thermocouple sensing
* Heater control through the SSR
* Fan motor control
* Power conversion hardware

---

# Airflow Development

Following the airflow issues identified during earlier testing, a new fan was designed and manufactured using PETG through 3D printing.

Testing showed improved bean movement within the roasting chamber, helping achieve more effective fluidisation during roasting.

The team has recorded videos of the roasting process to support testing and evaluation.

---

# Safety and Electrical Design

Progress has also been made on improving system safety.

The mains-powered sections of the system have now been enclosed to reduce exposure to high-voltage components. Work is ongoing to further improve enclosure of the remaining low-voltage electronics.

---

# Control System Development

Development of the roasting control system has continued significantly since the previous update.

Initial testing was performed using PID control. While functional, the team found that temperature overshoot could be reduced through alternative control methods.

As a result, the project has begun transitioning towards Model Predictive Control (MPC), which has shown improved temperature regulation during testing.

The current system is capable of:

* Monitoring roast temperature
* Controlling heater operation
* Controlling airflow
* Executing automated roast profiles

---

# User Interface Development

The user interface has continued to evolve and now provides greater control over the roasting process.

Current functionality includes:

* Real-time temperature graphing
* Roast temperature selection
* Preset roast profiles
* Start Roast control
* Stop & Cool control
* Emergency Stop functionality

Preset profiles currently correspond to different roast levels, allowing users to select their desired roast more easily.

---

# Current System Status

The project has now achieved its minimum viable functionality.

The current prototype is capable of:

* Roasting coffee beans successfully
* Monitoring temperature in real time
* Controlling heater output
* Controlling airflow
* Running roast profiles
* Cooling beans after roasting
* Providing user interaction through the graphical interface

AI functionality has not yet been implemented, as the current focus has been on establishing a stable and reliable roasting platform.

---

# Next Steps

The next phase of development is expected to include:

* Further enclosure improvements
* Addition of a second thermocouple for improved monitoring and control
* Integration of a dedicated display for the user interface
* Investigation of camera-based AI features
* Refinement of the roasting control algorithm

Future updates will focus on system refinement and AI-assisted roasting capabilities.