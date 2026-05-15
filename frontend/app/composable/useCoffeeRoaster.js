import { ref } from 'vue';

const socket = ref(null);
const isConnected = ref(false);
const lastError = ref(null);

// The current real-time state of the machine
const liveData = ref({
    timestamp: 0,
    temp: 20.0,
    targetTemp: 0.0,
    ror: 0.0,
    heaterPwm: 0,
    fanPwm: 0,
    state: "IDLE" // IDLE, PREHEAT, ROASTING, COOLING, ERROR
});

// Array to feed into Chart.js / vue-chartjs
const roastDataPoints = ref([]);

export const useCoffeeRoaster = () => {
    const connect = () => {
        if (socket.value && socket.value.readyState === WebSocket.OPEN) return;

        const wsUrl = "ws://127.0.0.1:8000/ws/telemetry";
        console.log(`Connecting to ${wsUrl}`);

        socket.value = new WebSocket(wsUrl);

        socket.value.onopen = () => {
            isConnected.value = true;
            lastError.value = null;
            console.log('WebSocket connection established.');
            getSystemState();
        };

        socket.value.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);

                if (message.type === "telemetry") {
                    liveData.value = {
                        timestamp: message.timestamp,
                        temp: message.temp,
                        targetTemp: message.target,
                        ror: message.ror,
                        heaterPwm: message.heater_pwm,
                        fanPwm: message.fan_pwm,
                        state: message.state
                    };

                    // Only record points if we are actually roasting or cooling
                    if (message.state !== "IDLE") {
                        roastDataPoints.value.push({...liveData.value});
                    }
                } else if (message.type === "system_state") {
                    console.log("Hardware Synced:", message);
                    liveData.value.state = message.state;
                } else if (message.type === "error") {
                    lastError.value = message.msg;
                    console.error("Roaster Error:", message.msg);
                }
            } catch (e) {
                console.error('Error parsing WebSocket message:', e);
            }
        };

        socket.value.onclose = () => {
            isConnected.value = false;
            socket.value = null;
            setTimeout(connect, 3000); // Auto-reconnect every 3 seconds
        };

        socket.value.onerror = (error) => {
            isConnected.value = false;
            console.error('WebSocket error:', error);
        };
    };

    const disconnect = () => {
        if (socket.value) {
            socket.value.close();
        }
    };

    // --- CONTROL ENDPOINTS ---

    const startRoast = (profileId) => {
        if (!isConnected.value) return;
        roastDataPoints.value =[]; // Clear chart history
        socket.value?.send(JSON.stringify({
            action: 'START_ROAST',
            profile_id: profileId
        }));
    };

    // Normal Stop: Turns off heater, leaves fan ON to cool beans safely
    const stopRoast = () => {
        if (!isConnected.value) return;
        socket.value?.send(JSON.stringify({ action: 'STOP_ROAST' }));
    };

    // Emergency Stop: Kills EVERYTHING immediately (Safety Requirement)
    const emergencyStop = () => {
        if (!isConnected.value) return;
        socket.value?.send(JSON.stringify({ action: 'E_STOP' }));
    };

    const getSystemState = () => {
        if (!isConnected.value) return;
        socket.value?.send(JSON.stringify({ action: 'GET_STATE' }));
    };

    return {
        connect,
        disconnect,
        isConnected,
        lastError,
        liveData,
        roastDataPoints,
        startRoast,
        stopRoast,
        emergencyStop,
        getSystemState
    };
};