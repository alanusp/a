const state = {
  events: [],
  chartData: [],
  maxPoints: 60,
};

window.htmx = {
  onLoad(callback) {
    callback(document);
  },
};

window.Alpine = {
  start() {},
};

class MiniPlot {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
  }

  update(points) {
    const ctx = this.ctx;
    const { width, height } = this.canvas;
    ctx.clearRect(0, 0, width, height);
    if (!points.length) {
      return;
    }
    ctx.beginPath();
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2;
    points.forEach((value, index) => {
      const x = (index / (points.length - 1 || 1)) * width;
      const y = height - value * height;
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();
  }
}

window.uPlot = MiniPlot;

function renderEvents() {
  const tbody = document.getElementById("events");
  tbody.innerHTML = state.events
    .slice(-state.maxPoints)
    .reverse()
    .map(
      (event) => `
        <tr>
          <td>${event.transaction_id}</td>
          <td>${event.probability.toFixed(4)}</td>
          <td>${event.decision}</td>
          <td>${event.latency_ms.toFixed(2)}</td>
        </tr>
      `,
    )
    .join("");
}

function updateChart(plot) {
  plot.update(state.chartData.slice(-state.maxPoints));
}

function appendInsight(event) {
  const insight = document.getElementById("insight-log");
  const entry = `#${event.transaction_id} → ${event.decision.toUpperCase()} (${(
    event.probability * 100
  ).toFixed(2)}% risk)`;
  insight.textContent = entry;
  if (event.audit_root) {
    const auditNode = document.getElementById("audit-root");
    auditNode.textContent = event.audit_root;
  }
  if (event.guardrail) {
    const guardrailNode = document.getElementById("guardrail-status");
    guardrailNode.textContent = event.guardrail;
    guardrailNode.className = event.guardrail === "ALLOW" ? "ok" : "warn";
  }
}

function startStream() {
  const eventSource = new EventSource("/v1/console/stream", {
    withCredentials: false,
  });
  const plot = new MiniPlot(document.getElementById("probability-chart"));

  eventSource.onmessage = (message) => {
    try {
      const payload = JSON.parse(message.data);
      state.events.push(payload);
      state.chartData.push(payload.probability);
      renderEvents();
      updateChart(plot);
      appendInsight(payload);
    } catch (error) {
      console.error("Failed to parse event", error);
    }
  };

  eventSource.onerror = () => {
    appendInsight({
      transaction_id: "system",
      decision: "error",
      probability: 0,
    });
  };
}

htmx.onLoad(startStream);
