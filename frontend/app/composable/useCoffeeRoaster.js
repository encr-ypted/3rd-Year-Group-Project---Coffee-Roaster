import { ref } from 'vue';

const socket = ref(null);
const isConnected = ref(false);
const lastError = ref(null);

const liveData = ref({
    timestamp: 0,
    temp: 20.0,
    targetTemp: 0.0,
    ror: 0.0,
    heaterPwm: 0,
    fanPwm: 0,
    state: "IDLE"
});

const roastDataPoints = ref([]);

const sendJson = (payload) => {
    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) return false;
    socket.value.send(JSON.stringify(payload));
    return true;
};

export const useCoffeeRoaster = () => {
    const connect = () => {
        if (socket.value && socket.value.readyState === WebSocket.OPEN) return;

        const wsUrl = "ws://10.64.26.141:8000/ws/telemetry";
        socket.value = new WebSocket(wsUrl);

        socket.value.onopen = () => {
            isConnected.value = true;
            lastError.value = null;
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

                    if (message.state !== "IDLE") {
                        roastDataPoints.value.push({ ...liveData.value });
                    }
                } else if (message.type === "system_state") {
                    liveData.value.state = message.state;
                } else if (message.type === "error") {
                    lastError.value = message.msg;
                }
            } catch (e) {
                console.error('Error parsing WebSocket message:', e);
            }
        };

        socket.value.onclose = () => {
            isConnected.value = false;
            socket.value = null;
            setTimeout(connect, 3000);
        };

        socket.value.onerror = () => {
            isConnected.value = false;
        };
    };

    const disconnect = () => {
        socket.value?.close();
    };

    const startRoast = (profileId) => {
        if (!isConnected.value) return;
        roastDataPoints.value = [];
        sendJson({ action: 'START_ROAST', profile_id: profileId });
    };

    const stopRoast = () => {
        if (!isConnected.value) return;
        sendJson({ action: 'STOP_ROAST' });
    };

    const emergencyStop = () => {
        if (!isConnected.value) return;
        sendJson({ action: 'E_STOP' });
    };

    const getSystemState = () => {
        sendJson({ action: 'GET_STATE' });
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
