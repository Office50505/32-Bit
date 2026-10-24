# ProvenanceLab for iOS

Native SwiftUI client for the existing ProvenanceLab FastAPI backend. The web frontend and backend are unchanged.

## Requirements

- Xcode 16 or newer
- iOS 17 or newer
- The ProvenanceLab backend running locally or deployed over HTTPS

## Run

1. Start the existing backend from the repository root:

   ```bash
   .venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000
   ```

2. Open `ios/ProvenanceLabIOS.xcodeproj` in Xcode.
3. Select the `ProvenanceLab` scheme and an iPhone Simulator.
4. Build and run.
5. In the app, open **Server Settings**. Use `http://127.0.0.1:8000` in Simulator. For a physical iPhone, use the Mac's LAN address while both devices are on the same network, or use a production HTTPS URL.

## App Store setup

- Set your Apple development team and final bundle identifier in the target's Signing & Capabilities panel.
- Review the included 1024×1024 icon in `Assets.xcassets/AppIcon.appiconset/AppIcon.png` and replace it only if the product mark changes.
- Use an HTTPS API deployment for release builds. The project permits local-network discovery for development but does not enable arbitrary cleartext internet traffic.
- Configure `FAL_KEY` only on the backend. The iOS app never stores or transmits that secret directly.

## Feature map

- Direct SMILES, PDF, image, and CSV source intake
- On-device SHA-256 source hashing
- MolNexTR image extraction through the existing backend
- RDKit candidate confirmation and reproducible run creation
- Validation findings, standardization, properties, provenance, and evidence state
- Multi-molecule comparison
- Backend-generated PDF export through the iOS share sheet
- Project-scoped Benzo assistant with current-molecule context
- Restores the most recent run across launches
- Dynamic Type, dark-mode-aware system surfaces, reduced-motion support, cancellation, and native navigation
