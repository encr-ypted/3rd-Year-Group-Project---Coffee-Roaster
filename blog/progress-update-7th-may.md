# Smart Coffee Roaster – Progress Update
## 7 May 2026

---

# Introduction

Our project focuses on developing an AI-enabled small batch coffee roasting machine that addresses sustainability and accessibility challenges within coffee roasting.

The project combines embedded systems, sensing, control engineering, and AI technologies to create a low-cost intelligent coffee roaster capable of producing consistent roast profiles while improving user experience and safety.

Our current concept is based around modifying a hot-air popcorn popper into a fluidised bed coffee roaster platform.

---

# Sustainability Motivation

Coffee roasting presents several sustainability challenges including:

- Energy consumption
- Waste from inconsistent roasting
- Limited accessibility to affordable roasting equipment
- Dependence on large-scale commercial roasting systems

Our goal is to explore how intelligent monitoring and control can improve roast consistency while reducing waste and improving accessibility.

---

# IBM Onboarding Progress

All team members have completed the following onboarding tasks:

- IBM Design Thinking for Academia badge
- Two IBM AI SkillsBuild badges

These activities helped establish a shared understanding of AI concepts, collaboration, and design thinking methodologies.

---

# Initial Technical Research

Our team researched DIY coffee roasting systems, particularly fluidised bed roasters based on popcorn poppers.

From this research, we identified several important engineering challenges:

- Maintaining stable temperature profiles
- Ensuring sufficient airflow for even roasting
- Preventing overheating
- Achieving roast repeatability
- Managing safe cooling after roasting
- Improving overall system safety

We also researched coffee roasting phases including:
- Drying phase
- Maillard reaction
- First crack
- Development phase
- Cooling phase

This highlighted the importance of sensing and closed-loop control.

---

# Early System Concept

## Proposed Sensing
- Bean temperature sensing
- Air temperature sensing
- Potential future airflow and power sensing

## Proposed Control
- Fan speed control
- Heater power control
- Roast profile tracking
- Cooling mode control

## Proposed AI Features
- Roast data logging
- Roast profile recommendations
- AI-assisted optimisation
- Future dashboard or analytics system

At this stage, the architecture is still evolving and may change during prototyping.

---

# MoSCoW Requirements

## Must Have
- The system must use a Raspberry Pi as the main controller.
- The system must measure real-time temperature using a K-type thermocouple and MAX6675 or MAX31855 module.
- The system must implement a PID control loop for thermal control.
- The system must control heater output using an SSR or MOSFET-based power electronic switching method.
- The system must provide basic fan or airflow operation to support bean agitation and safety.
- The system must include safety shutdown logic for dangerous conditions.
- The system must log roast data such as temperature, time, and heater output.
- The system must include a basic dashboard for live monitoring.
- The system must complete a functional demonstration roast or controlled heating test.
- The system must include a technical report and Git repository.

## Should Have
- The system should provide an internet-accessible remote dashboard.
- The system should provide a mobile application dashboard.
- The dashboard should include secure access control.
- The system should calculate and display Rate of Rise.
- The dashboard should display roast phase indicators such as drying, Maillard, and development.
- The system should support light, medium, and dark roast profiles.
- The project should show clear IBM Granite usage for code optimisation, testing, documentation, and analysis.
- The final report should include a reflection on how IBM SkillsBuild improved the development workflow.
- The project should include safety testing and documented fault responses.

## Could Have
- The system could include machine learning-based roast suggestions.
- The system could include automatic PID tuning support.
- The system could store data in a cloud database.
- The dashboard could include advanced graphs and comparison between roast curves.
- The system could store multiple bean profiles.
- The system could recommend future roast settings based on previous roast data.

## Won’t Have (For Now)
- The project will not build a commercial coffee roasting product.
- The project will not support large-batch roasting.
- The project will not include voice assistant control.
- The project will not create a fully automated machine learning roaster as a core requirement.
- The project will not build a complete carbon-emissions model.
- The project will not focus on advanced mechanical redesign unless time allows.
- The project will not depend on cloud infrastructure for the basic system to function.

---

# Initial User Journey

1. User loads green coffee beans into the roaster.
2. User selects a roast profile.
3. Sensors monitor the roasting process.
4. The control system adjusts heater power and airflow.
5. Roast data is logged throughout the roast.
6. Cooling mode activates automatically.
7. User reviews roast results and analytics.

---

# Current Planning and Procurement

Our team is currently preparing to purchase:
- A popcorn popper base system
- Temperature sensing components
- Control electronics
- Additional safety-related hardware

We are also evaluating:
- Sensor options
- Microcontroller platforms
- Safe power control approaches
- AI integration methods

---

# Next Steps

Our next development phase will include:

- Component procurement and breadboard testing of the sensor/control loop.
- Chassis modification and safety-critical wiring (AC side isolation).
- Software development (PID tuning and web dashboard implementation).
