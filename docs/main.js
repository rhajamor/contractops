const benchmarkModels = [
  {
    name: "llama3.1:8b",
    passRate: 40,
    contractRate: 90,
    latencyMs: 3411,
    tokensPerSecond: 110.3,
  },
  {
    name: "deepseek-r1:8b",
    passRate: 30,
    contractRate: 86,
    latencyMs: 6383,
    tokensPerSecond: 98.3,
  },
  {
    name: "qwen3:8b",
    passRate: 20,
    contractRate: 85,
    latencyMs: 6970,
    tokensPerSecond: 98.7,
  },
  {
    name: "gpt-oss:20b",
    passRate: 20,
    contractRate: 85,
    latencyMs: 6954,
    tokensPerSecond: 60.5,
  },
  {
    name: "phi4-mini",
    passRate: 20,
    contractRate: 86,
    latencyMs: 19980,
    tokensPerSecond: 10.0,
  },
  {
    name: "mistral:7b",
    passRate: 20,
    contractRate: 83,
    latencyMs: 4750,
    tokensPerSecond: 102.6,
  },
  {
    name: "gemma3:4b",
    passRate: 10,
    contractRate: 78,
    latencyMs: 4530,
    tokensPerSecond: 155.4,
  },
];

const chartTextPlugin = {
  id: "chartTextPlugin",
  afterDatasetsDraw(chart) {
    if (chart.canvas.id !== "latencyThroughputChart") {
      return;
    }

    const { ctx } = chart;
    const dataset = chart.data.datasets[0];

    ctx.save();
    ctx.font = "12px Inter, sans-serif";
    ctx.fillStyle = "rgba(208, 224, 255, 0.9)";

    dataset.data.forEach((point, index) => {
      const position = chart.getDatasetMeta(0).data[index].getProps(["x", "y"], true);
      const label = point.label;
      ctx.fillText(label, position.x + 8, position.y - 8);
    });

    ctx.restore();
  },
};

function createPassContractChart() {
  const canvas = document.getElementById("passContractChart");
  if (!canvas) {
    return;
  }

  new Chart(canvas, {
    type: "bar",
    data: {
      labels: benchmarkModels.map((model) => model.name),
      datasets: [
        {
          label: "Scenario Pass Rate (%)",
          data: benchmarkModels.map((model) => model.passRate),
          backgroundColor: "rgba(95, 134, 255, 0.72)",
          borderColor: "rgba(149, 183, 255, 1)",
          borderWidth: 1.5,
          borderRadius: 8,
        },
        {
          label: "Contract Compliance (%)",
          data: benchmarkModels.map((model) => model.contractRate),
          backgroundColor: "rgba(31, 232, 214, 0.7)",
          borderColor: "rgba(136, 248, 236, 1)",
          borderWidth: 1.5,
          borderRadius: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          ticks: { color: "rgba(196, 213, 242, 0.9)", maxRotation: 24, minRotation: 24 },
          grid: { color: "rgba(122, 149, 209, 0.15)" },
        },
        y: {
          beginAtZero: true,
          max: 100,
          ticks: { color: "rgba(196, 213, 242, 0.9)" },
          grid: { color: "rgba(122, 149, 209, 0.15)" },
        },
      },
      plugins: {
        legend: {
          labels: { color: "rgba(223, 235, 255, 0.95)" },
        },
      },
    },
  });
}

function createLatencyThroughputChart() {
  const canvas = document.getElementById("latencyThroughputChart");
  if (!canvas) {
    return;
  }

  new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Models",
          data: benchmarkModels.map((model) => ({
            x: model.latencyMs,
            y: model.tokensPerSecond,
            label: model.name,
          })),
          pointRadius: benchmarkModels.map((model) => 4 + model.passRate / 10),
          pointHoverRadius: 10,
          pointBackgroundColor: "rgba(122, 157, 255, 0.78)",
          pointBorderColor: "rgba(199, 219, 255, 1)",
          pointBorderWidth: 1.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          title: {
            display: true,
            text: "Avg latency (ms, lower is better)",
            color: "rgba(205, 221, 248, 0.92)",
          },
          ticks: { color: "rgba(196, 213, 242, 0.9)" },
          grid: { color: "rgba(122, 149, 209, 0.15)" },
        },
        y: {
          title: {
            display: true,
            text: "Tokens/sec (higher is better)",
            color: "rgba(205, 221, 248, 0.92)",
          },
          ticks: { color: "rgba(196, 213, 242, 0.9)" },
          grid: { color: "rgba(122, 149, 209, 0.15)" },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(context) {
              const point = context.raw;
              return `${point.label}: ${point.x}ms, ${point.y} tok/s`;
            },
          },
        },
      },
    },
    plugins: [chartTextPlugin],
  });
}

function createFailureModesChart() {
  const canvas = document.getElementById("failureModesChart");
  if (!canvas) {
    return;
  }

  new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: [
        "Exceeded max_chars",
        "Missing required tool calls",
        "Missing must_include language",
        "Policy/safety boundary slips",
      ],
      datasets: [
        {
          data: [38, 31, 19, 12],
          backgroundColor: [
            "rgba(95, 134, 255, 0.78)",
            "rgba(31, 232, 214, 0.78)",
            "rgba(165, 126, 255, 0.78)",
            "rgba(255, 124, 171, 0.78)",
          ],
          borderColor: "rgba(13, 19, 38, 0.8)",
          borderWidth: 2,
          hoverOffset: 10,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: "rgba(216, 230, 255, 0.95)",
            boxWidth: 14,
          },
        },
      },
      cutout: "58%",
    },
  });
}

function initMetricCounters() {
  const counters = document.querySelectorAll("[data-count]");
  if (counters.length === 0) {
    return;
  }

  counters.forEach((counter) => {
    const target = Number(counter.getAttribute("data-count") || "0");
    const durationMs = 950;
    const start = performance.now();

    const frame = (time) => {
      const progress = Math.min((time - start) / durationMs, 1);
      counter.textContent = Math.floor(progress * target).toString();
      if (progress < 1) {
        requestAnimationFrame(frame);
      } else {
        counter.textContent = target.toString();
      }
    };

    requestAnimationFrame(frame);
  });
}

function initMobileMenu() {
  const menuToggle = document.getElementById("menuToggle");
  const nav = document.getElementById("siteNav");

  if (!menuToggle || !nav) {
    return;
  }

  menuToggle.addEventListener("click", () => {
    nav.classList.toggle("open");
  });

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => nav.classList.remove("open"));
  });
}

function initActiveSectionLinks() {
  const links = [...document.querySelectorAll("nav a")];
  const sections = links
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);

  const sectionById = new Map(sections.map((section) => [section.id, section]));

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) {
          return;
        }
        links.forEach((link) => {
          const target = link.getAttribute("href").replace("#", "");
          const isActive = target === entry.target.id;
          link.classList.toggle("active", isActive);
        });
      });
    },
    { rootMargin: "-40% 0px -45% 0px", threshold: 0.1 },
  );

  sectionById.forEach((section) => observer.observe(section));
}

function initCharts() {
  if (typeof Chart === "undefined") {
    return;
  }

  Chart.defaults.color = "rgba(216, 230, 255, 0.95)";
  Chart.defaults.font.family = "Inter, sans-serif";
  Chart.defaults.plugins.tooltip.backgroundColor = "rgba(5, 10, 24, 0.95)";
  Chart.defaults.plugins.tooltip.borderColor = "rgba(144, 168, 232, 0.3)";
  Chart.defaults.plugins.tooltip.borderWidth = 1;

  createPassContractChart();
  createLatencyThroughputChart();
  createFailureModesChart();
}

window.addEventListener("DOMContentLoaded", () => {
  initMetricCounters();
  initMobileMenu();
  initActiveSectionLinks();
  initCharts();
});
