hospitalfullstack
Hospital Management System – Backend API
A robust, production-ready backend API built with Django and Django REST Framework for managing hospital operations.
This system powers user authentication, appointment workflows, staff coordination, medical records, and an admin-managed blog.

🔗 Live Links
Live API Base URL: https://dhospitalback.onrender.com/api/
Frontend Demo (separate project): https://ettahospitalclone.vercel.app
🚀 Key Features
🔐 Role-Based Authentication & Authorization
Supported roles: Patient, Doctor, Nurse, Lab Scientist, Admin
Custom Profile model with role-specific permissions
JWT authentication (access & refresh tokens)
Google OAuth authentication support
🗓 Appointment Workflow
Patients book appointments with automatic or random doctor assignment
Doctors assign nurses for vitals and lab scientists for tests
Nurses record vital signs
Lab scientists submit lab results
Doctors issue final medical reports and complete appointments
🖼 Media Handling
Profile images and blog media stored on AWS S3
Public-read access with robust upload handling
Logging and fallback mechanisms for failed uploads
📝 Blog System (Admin Only)
Rich text blog posts with featured images
Automatic table of contents and subheading generation
Blog images synced to AWS S3 on save
🔒 Security & Production Readiness
CORS configured for frontend integration
CSRF and secure cookies for social authentication
Redis caching support (with local-memory fallback)
Whitenoise for static file handling
Environment-based configuration using .env
🛠 Tech Stack
Backend
Django 4.x
Django REST Framework
JWT Authentication (SimpleJWT)
Google OAuth (Social Auth)
Infrastructure
Database: PostgreSQL (Render-hosted)
Media Storage: AWS S3 (django-storages)
Caching: Redis
Deployment: Render (Gunicorn)
Other Tools:
django-decouple, dj-database-url, corsheaders, whitenoise