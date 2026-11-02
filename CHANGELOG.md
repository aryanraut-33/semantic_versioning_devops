# Changelog

## [2.0.0]

- Split React/Nginx and Flask/Gunicorn into separate containers; update CI, paired-image deployment/recovery, and release evidence.

- Add distinct browser URLs for calculator modes, results, and formula explanations, with direct-link support.

- Replace the documented arithmetic form at `/` with CalFit, a responsive React and TypeScript fitness calculator (breaking UI contract change).
- Add calorie, BMI, combined fitness, and activity-options APIs with validated metric and US measurements.
- Document Mifflin–St Jeor resting energy, activity factors, adult BMI categories, and estimate limitations.
- Remove all arithmetic routes and the old HTML template; preserve health and release identity endpoints.
- Build the frontend inside Docker and extend automated tests and packaged HTTP verification.

## [1.0.1]

- Correct punctuation and capitalization in the calculator introduction.
