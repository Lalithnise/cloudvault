document.addEventListener("DOMContentLoaded", function () {
    const clickSound = new Audio("/static/sounds/click.mp3");
    document.querySelectorAll("button, a").forEach(elem => {
        elem.addEventListener("click", () => {
            clickSound.play();
        });
    });
});
