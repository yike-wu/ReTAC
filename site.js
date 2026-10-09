const config = window.RETAC_SITE;

document.querySelector("#authors").innerHTML = config.authors.join(" &nbsp; ");
document.querySelector("#affiliation").innerHTML = config.affiliation;
document.querySelector("#paper-link").href = config.paperUrl;

for (const [key, selector] of [["arxivUrl", "#arxiv-link"], ["codeUrl", "#code-link"]]) {
  if (config[key]) {
    const link = document.querySelector(selector);
    link.href = config[key];
    link.hidden = false;
  }
}

const dialog = document.querySelector("#citation-dialog");
document.querySelector("#bibtex").textContent = config.bibtex;
document.querySelector("#cite-button").addEventListener("click", () => dialog.showModal());
document.querySelector("#close-dialog").addEventListener("click", () => dialog.close());
document.querySelector("#copy-bibtex").addEventListener("click", async (event) => {
  await navigator.clipboard.writeText(config.bibtex);
  event.currentTarget.textContent = "Copied";
  setTimeout(() => { event.currentTarget.textContent = "Copy BibTeX"; }, 1400);
});
