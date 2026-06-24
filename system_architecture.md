# System Architecture

## Overview

The smart coffee roaster is built around a Raspberry Pi 4 which acts as the central controller for the roasting system.

The Raspberry Pi interfaces with the temperature sensing hardware, heater, fan, camera system, and user interface while executing the roasting control algorithm.

---

## Hardware Architecture

### Temperature Measurement

A K-type thermocouple connected through a MAX31855 interface is used to measure bean temperature during roasting.

Temperature measurements are continuously read by the Raspberry Pi and used by the control system.

### Heater Control

The heater is controlled through a Solid State Relay (SSR) connected to the Raspberry Pi.

The control algorithm adjusts heater output to follow the selected roast profile.

### Fan Control

The roasting fan is controlled by the Raspberry Pi and is used for bean circulation during roasting and cooling airflow after roasting.

### Camera System

A Raspberry Pi camera monitors the beans throughout the roast.

Image data is processed separately from the main roasting controller to prevent camera failures from interrupting the roasting process.

---

## Software Architecture

The software consists of three main components:

### Control System

Responsible for:

* Reading temperature measurements
* Executing the MPC control algorithm
* Controlling heater output
* Controlling fan operation
* Applying safety logic

### Camera Monitoring

Responsible for:

* Capturing images of the beans
* Performing grayscale analysis
* Monitoring roast progression

### Web Interface

Provides:

* Real-time temperature display
* Roast profile selection
* Start Roast control
* Stop & Cool control
* Emergency Stop control

---

## Data Flow

1. Temperature data is read from the thermocouple.
2. The control system calculates the required heater output.
3. Heater and fan outputs are updated.
4. Temperature and roast information are sent to the web interface.
5. Camera monitoring runs in parallel and provides roast progression feedback.

---

## Safety Features

The system includes:

* Emergency Stop functionality
* Controlled cooling mode
* Enclosed mains and low voltage wiring
* Temperature monitoring and protection

Emergency Stop immediately disables roasting operation, while Stop & Cool disables the heater and continues airflow for safe cooling.
