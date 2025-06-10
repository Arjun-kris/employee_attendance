# 🕒 Employee Attendance - Frappe ERPNext v15 App

A custom Frappe app for managing employee attendance via device integrations and log syncing. Designed for ERPNext v15 environments.

---

## 🔧 Features

- Log employee attendance based on device inputs
- Supports `IN` and `OUT` type logs
- Integration-ready with biometric/RFID systems
- Uses `attendance_device_id` for matching employee records
- Simple REST API for log submission

---

## 🚀 Installation

```bash
# Get the app
git clone https://github.com/Arjun-kris/employee_attendance.git

# Go to your bench directory
cd frappe-bench

# Get into your site
bench --site your-site-name install-app employee_attendance

# Migrate the site
bench migrate

```

---

## 📲 API Usage

- Endpoint:
  ```bash
  /api/method/hrms.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field
  ```

- Sample payload:
  ```bash
  {
  "employee_field": "attendance_device_id",
  "employee_field_value": "EMP001",
  "timestamp": "2025-06-10 09:00:00",
  "device_id": "DEVICE01",
  "log_type": "IN"
  }
  ```

---

## 📌 Notes
- Ensure attendance_device_id is correctly set on each Employee record.
- Requires HRMS module to be installed and enabled.
- Best used in environments with physical access control systems.


