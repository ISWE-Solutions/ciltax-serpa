console.log("Tab Title JS is being executed");

(function () {
    const desiredTitle = "Smart Invoice";

    // Function to update the title
    function updateTitle() {
        if (document.title !== desiredTitle) {
            document.title = desiredTitle;
            console.log("Tab title updated to:", desiredTitle);
        }
    }

    // Check and update the title every 500ms
    setInterval(updateTitle, 500);
})();
