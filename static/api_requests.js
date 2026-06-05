function fetchLiveFixtures() {
  return fetch("https://v3.football.api-sports.io/fixtures?live=all", {
    headers: {
      "x-apisports-key": "bcdc5117afe4321a42a599f76f50ccb7",
    },
  });
}

console.log("Fetching live football fixtures...");

fetchLiveFixtures()
  .then((response) => {
    if (!response.ok) {
      throw new Error("Network response was not ok");
    }
    return response.json();
  })
  .then((data) => {
    console.log("Live football fixtures:", data);
  })
  .catch((error) => {
    console.error("Error fetching live football fixtures:", error);
  });
