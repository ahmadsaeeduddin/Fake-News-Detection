class FakeNewsDetector {
  constructor() {
    this.baseURL = "http://172.22.96.1:5000"; // Backend server URL
    this.initializeEventListeners();
  }

  initializeEventListeners() {
    document.getElementById("analyzeClaimBtn").addEventListener("click", () => {
      this.analyzeClaim();
    });

    document.getElementById("analyzeUrlBtn").addEventListener("click", () => {
      this.analyzeUrl();
    });

    document.getElementById("claimInput").addEventListener("keypress", (e) => {
      if (e.key === "Enter" && e.ctrlKey) {
        this.analyzeClaim();
      }
    });

    document.getElementById("urlInput").addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        this.analyzeUrl();
      }
    });
  }

  async analyzeClaim() {
    const claimText = document.getElementById("claimInput").value.trim();
    if (!claimText) {
      this.showError("claimError", "Please enter a claim to analyze.");
      return;
    }

    this.setLoading("analyzeClaimBtn", true);
    this.hideError("claimError");
    this.hideResults("claimResults");
    this.showProgress("claimProgress", "claimStep");

    try {
      const steps = [
        "Extracting keywords...",
        "Searching for related information...",
        "Building knowledge base...",
        "Running fact-check analysis...",
        "Generating results...",
      ];

      let currentStep = 0;
      const stepInterval = setInterval(() => {
        if (currentStep < steps.length) {
          this.updateProgress(
            "claimProgress",
            "claimStep",
            (currentStep + 1) * 20,
            steps[currentStep]
          );
          currentStep++;
        }
      }, 1000);

      const response = await fetch(`${this.baseURL}/analyze-claim`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ claim: claimText }),
      });

      clearInterval(stepInterval);
      this.updateProgress("claimProgress", "claimStep", 100, "Analysis complete!");

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const result = await response.json();
      this.displayResults("claimResults", result, "claim");
    } catch (error) {
      this.showError(
        "claimError",
        "Failed to analyze claim. Please check your connection and try again."
      );
    } finally {
      this.setLoading("analyzeClaimBtn", false);
      setTimeout(() => this.hideProgress("claimProgress", "claimStep"), 2000);
    }
  }

  async analyzeUrl() {
    const url = document.getElementById("urlInput").value.trim();
    if (!url) {
      this.showError("urlError", "Please enter a valid URL.");
      return;
    }
    if (!this.isValidUrl(url)) {
      this.showError("urlError", "Please enter a valid URL (e.g., https://example.com)");
      return;
    }

    this.setLoading("analyzeUrlBtn", true);
    this.hideError("urlError");
    this.hideResults("urlResults");
    this.showProgress("urlProgress", "urlStep");

    try {
      const steps = [
        "Scraping article content...",
        "Cleaning and processing text...",
        "Generating claims...",
        "Extracting keywords...",
        "Building knowledge base...",
        "Running fact-check analysis...",
      ];

      let currentStep = 0;
      const stepInterval = setInterval(() => {
        if (currentStep < steps.length) {
          this.updateProgress(
            "urlProgress",
            "urlStep",
            (currentStep + 1) * 16.67,
            steps[currentStep]
          );
          currentStep++;
        }
      }, 2000);

      const response = await fetch(`${this.baseURL}/analyze-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url }),
      });

      clearInterval(stepInterval);
      this.updateProgress("urlProgress", "urlStep", 100, "Analysis complete!");

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const result = await response.json();
      this.displayResults("urlResults", result, "url");
    } catch (error) {
      this.showError(
        "urlError",
        "Failed to analyze article. Please check the URL and try again."
      );
    } finally {
      this.setLoading("analyzeUrlBtn", false);
      setTimeout(() => this.hideProgress("urlProgress", "urlStep"), 2000);
    }
  }

  extractClassification(text) {
  // Case 1: Explicit "**Classification:** **XYZ**"
    const classificationRegex = /\*\*Classification:\*\*\s*\*\*(.*?)\*\*/i;
    const match = text.match(classificationRegex);
    if (match && match[1]) {
      return match[1].trim();
    }

    // Case 2: First bold-only word (e.g., "**Supported**")
    const boldMatches = [...text.matchAll(/\*\*(.*?)\*\*/g)];
    if (boldMatches.length > 0) {
      return boldMatches[0][1].trim();
    }

    return "Unknown";
  }

  cleanJustification(text) {
    return text
      // Remove classification section entirely
      .replace(/\*\*Classification:\*\*.*(\r?\n)?/i, "")
      .replace(/^\s*\*\*(Supported|Refuted|Unsupported|Unknown)\*\*\s*/i, "")
      // Remove justification headers
      .replace(/\*\*Justification:\*\*/i, "")
      .replace(/Justification:/i, "")
      // Convert bullets
      .replace(/^\s*[\*\-]\s+/gm, "<li>")
      // Wrap multiple li into <ul>
      .replace(/(<li>.*?)(?=(?:<li>|$))/gs, "$1</li>")
      .replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>")
      // Remove bold markers
      .replace(/\*\*(.*?)\*\*/g, "$1")
      // Normalize whitespace: collapse 2+ newlines into 1
      .replace(/\n{2,}/g, "\n")
      .replace(/^\s+|\s+$/g, "")
      .trim();
  }



  displayResults(containerId, result, type) {
    let html = "";
    if (type === "claim") {
      const claimText = result.claim || "N/A";
      const factCheckRaw = result.fact_check_result || "";
      const match = factCheckRaw.match(/\*\*(.*?)\*\*/);
      const finalResult = this.extractClassification(factCheckRaw);
      const justification = this.cleanJustification(factCheckRaw);

      html = `
      <h4 style="margin-bottom: 20px; color: #4CAF50;">Analysis Results</h4>
      <div class="result-item">
        <p><strong style="color:#1E88E5;">Claim:</strong> ${claimText}</p>
        <p><strong style="color:red;">Classification:</strong> ${finalResult}</p>
        <p><strong style="color:green;">Justification:</strong><br>
        <div style="white-space:normal; color: #eee;">${justification}</div></p>
        ${
            result.sources
            ? `<p><strong style="color:#6D4C41;">Sources:</strong> ${result.sources.length} sources analyzed</p>`
            : ""
        }
      </div>
     `;

    } else if (type === "url") {
      html = `<h4 style="margin-bottom: 20px; color: #4CAF50;">Article Analysis Results</h4>`;
      if (result.claims && result.claims.length > 0) {
        result.claims.forEach((claim, index) => {
          const factCheckRaw = claim.fact_check_result || "";
          const match = factCheckRaw.match(/\*\*(.*?)\*\*/);
          let finalResult = match ? match[1].trim() : "Unknown";
          finalResult = finalResult.replace(/^Classification:\s*/i, "");
          let justification = this.cleanJustification(factCheckRaw);

          html += `
            <div class="result-item">
                <div class="result-header">
                    <strong>Claim ${index + 1}</strong>
                    <span class="confidence-score">Score: ${claim.score || "N/A"}</span>
                </div>
                <p style='white-space:pre-wrap; margin-bottom:8px;'>${claim.text}</p>
                <p><strong style="color:red;">Classification:</strong> ${finalResult}</p>
                <p><strong style="color:green;">Justification:</strong><br>
                <div style="white-space:normal; color:#eee;">${justification}</div>
                </p>
            </div>
          `;
        });
      } else {
        html += `
          <div class="result-item">
              <p>Article analysis completed. ${
                result.message ||
                "No specific claims could be extracted for verification."
              }</p>
          </div>
        `;
      }
    }
    document.getElementById("modalResultContent").innerHTML = html;
    document.getElementById("resultModal").style.display = "flex";
    const container = document.getElementById(containerId);
    if (container) container.classList.remove("active");
  }

  setLoading(buttonId, isLoading) {
    const button = document.getElementById(buttonId);
    const loading = button.querySelector(".loading");
    button.disabled = isLoading;
    loading.classList.toggle("active", isLoading);
  }

  showError(errorId, message) {
    const errorElement = document.getElementById(errorId);
    errorElement.textContent = message;
    errorElement.classList.add("active");
  }

  hideError(errorId) {
    document.getElementById(errorId).classList.remove("active");
  }

  hideResults(resultsId) {
    document.getElementById(resultsId).classList.remove("active");
  }

  showProgress(progressId, stepId) {
    document.getElementById(progressId).classList.add("active");
    document.getElementById(stepId).classList.add("active");
  }

  hideProgress(progressId, stepId) {
    document.getElementById(progressId).classList.remove("active");
    document.getElementById(stepId).classList.remove("active");
  }

  updateProgress(progressId, stepId, percentage, stepText) {
    const progressFill = document.querySelector(`#${progressId} .progress-fill`);
    document.getElementById(stepId).textContent = stepText;
    progressFill.style.width = `${percentage}%`;
  }

  isValidUrl(string) {
    try {
      new URL(string);
      return true;
    } catch (_) {
      return false;
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  new FakeNewsDetector();

  // Sidebar logic
  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const closeSidebar = document.getElementById("closeSidebar");
  const overlay = document.getElementById("overlay");

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
      sidebar.classList.add("active");
      overlay.classList.add("active");
    });
  }

  if (closeSidebar) {
    closeSidebar.addEventListener("click", () => {
      sidebar.classList.remove("active");
      overlay.classList.remove("active");
    });
  }

  if (overlay) {
    overlay.addEventListener("click", () => {
      sidebar.classList.remove("active");
      overlay.classList.remove("active");
    });
  }
});


window.onload = function () {
  const modal = document.getElementById("resultModal");
  const closeBtn = document.getElementById("closeModal");
  closeBtn.onclick = () => modal.style.display = "none";
  window.onclick = (event) => {
    if (event.target === modal) modal.style.display = "none";
  };
};
