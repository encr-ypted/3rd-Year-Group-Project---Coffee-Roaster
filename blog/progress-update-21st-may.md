# Smart Coffee Roaster – Progress Update
## 21 May 2026

---

# Introduction

Since the previous update, the project has progressed from initial research and planning into early hardware prototyping and system testing.

Our team has focused on acquiring core components, investigating the popcorn popper platform, improving system safety, and beginning development of the control and software architecture required for the smart coffee roaster.

The current development approach is focused on first creating a minimum viable roasting system before gradually integrating more advanced features such as AI-assisted optimisation.

---

# Hardware Procurement and Components

A range of components have now been ordered or received to support early prototyping and testing.

## Components Ordered
- Popcorn popper
- Solid State Relay (SSR)
- K-type thermocouple
- MAX31855 thermocouple interface
- AC to DC converters
- WAGO connectors
- DPST switch
- Cabling and cable glands
- Enclosures
- Motor
- Heatsink
- Spade crimp connectors
- 3mm acrylic
- MOSFETs (IRF530N)
- Diodes (IN5408)
- BJTs (2N3904)
- Zener diodes

In addition, IBM has provided the team with a Raspberry Pi 4 platform to support software, control, and AI integration.

---

# Popcorn Popper Investigation and Testing

The popcorn popper has now been opened, inspected, and tested using coffee beans.

Initial testing showed that the beans did not circulate effectively enough for reliable fluidised bed roasting. As a result, the team has started developing an improved fan system, including the design and 3D printing of a new fan component to improve airflow and bean movement.

This testing phase helped identify several practical engineering considerations relating to airflow, thermal behaviour, and roasting consistency.

---

# Safety and Electrical Design

Safety has been an important consideration during early prototyping, particularly due to the use of mains.

The team identified risks associated with exposed wiring and AC mains connections during initial testing. To address this, additional safety-focused hardware was purchased, including:
- Protective enclosures
- Cable glands
- Improved cable management hardware

The current design approach aims to isolate and cover mains AC wiring while allowing safer access to lower-voltage sections of the system for development and testing purposes.

---

# Early Control System Development

Work has started on developing the control architecture for the roaster.

Current investigations and tests include:

- Initial closed-loop PID control experiments
- Heat gun testing as a safer substitute for the final heater during early development
- Observation of control output signals using an oscilloscope
- Early motor control testing for airflow regulation
- Testing of bean spinning and airflow mechanisms

These early experiments are helping the team better understand the thermal and dynamic behaviour of the system before integrating the final heating solution.

At this stage, AI functionality has not yet been implemented, as the current priority is establishing a stable and functional minimum-requirement roasting system.

---

# Software and Repository Development

The project repository has also evolved as development progresses. Its structure is intended to support future integration between hardware control, backend processing, frontend monitoring interfaces, and project documentation.

The team has also started testing an early user interface website as part of future monitoring and control development.

---

# Next Steps

The next phase of development is expected to include:

- Continued airflow and fan optimisation
- Integration of thermocouple temperature sensing
- Further motor control testing
- Initial heater control integration
- Expansion of the software and frontend systems
- Development of the first complete prototype circuit

Future updates will document the transition from early prototyping into integrated system testing.