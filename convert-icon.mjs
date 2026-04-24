const sharp = require("sharp");
const fs = require("fs");
const svgBuffer = fs.readFileSync("C:/Users/il90i/OneDrive/Desktop/cellcom--big.svg");
sharp(svgBuffer)
  .resize(256, 256)
  .png()
  .toFile("./custom_components/cellcom_energy/icon.png")
  .then(() => console.log("done"))
  .catch(e => console.error(e.message));
