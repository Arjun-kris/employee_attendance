import frappe
from frappe.utils import add_days, get_datetime, today, getdate, add_months, formatdate
from datetime import timedelta

@frappe.whitelist()
def get_date():
   today = frappe.utils.today()
   return today


@frappe.whitelist()
def get_user_details(email=None):
    if not email:
        return {"error": "Email parameter is required."}
    if email in ["Administrator", "silerp@softlandindia.co.in"]:
        return {
            "full_name": "MURALY G",
            "email": "silerp@softlandindia.co.in"
        }
    try:
        user = frappe.get_doc("Employee", {"user_id": email})
        
        return {
            "full_name": user.employee,
            "email": user.user_id
        }
    except frappe.DoesNotExistError:
        return {"error": "User not found."}
    except Exception as e:
        return {"error": str(e)}


@frappe.whitelist()
def get_main_attendance(employee_name, date):
    start_datetime = get_datetime(date + " 00:00:00")
    end_datetime = get_datetime(date + " 23:59:59")

    # Fetch first check-in & last check-out
    query = """
        SELECT `log_type`, `time`
        FROM `tabEmployee Checkin`
        WHERE `employee` = %s
        AND `time` BETWEEN %s AND %s
        ORDER BY `time` ASC
    """
    attendance_records = frappe.db.sql(query, (employee_name, start_datetime, end_datetime), as_dict=True)

    first_checkin = None
    last_logout = None
    total_working_seconds = 0
    current_session = {}

    for record in attendance_records:
        log_type = record["log_type"]
        log_time = record["time"]

        if log_type == "IN":
            if not first_checkin:
                first_checkin = log_time.strftime("%H:%M:%S")

            current_session["in_time"] = log_time

        elif log_type == "OUT":
            last_logout = log_time.strftime("%H:%M:%S")

            if "in_time" in current_session:
                working_seconds = (log_time - current_session["in_time"]).total_seconds()
                total_working_seconds += working_seconds
                current_session = {}  

    # Convert total working seconds to HH:MM:SS format
    total_hours = int(total_working_seconds // 3600)
    total_minutes = int((total_working_seconds % 3600) // 60)
    total_seconds = int(total_working_seconds % 60)
    total_working_hours = f"{total_hours}:{str(total_minutes).zfill(2)}:{str(total_seconds).zfill(2)}"

    # Get multi-level reportees
    report_hierarchy = get_all_reportees_api(employee_name, date)

    # Fetch employee details (Department & Custom Team)
    employee_details = frappe.db.get_value("Employee", {"employee": employee_name}, ["department", "custom_team"], as_dict=True)

    return {
        "employee_name": employee_name,
        "first_checkin": first_checkin if first_checkin else "-",
        "last_logout": last_logout if last_logout else "-",
        "department": employee_details["department"] if employee_details else "-",
        "custom_team": employee_details["custom_team"] if employee_details else "-",
        "total_working_hours": total_working_hours,
        "w_m_average": get_w_m_average(employee_name, date),
        "report_hierarchy": report_hierarchy
    }


@frappe.whitelist()
def get_attendance(employee_name, date):
    start_datetime = get_datetime(date + " 00:00:00")
    end_datetime = get_datetime(date + " 23:59:59")

    # Query Employee Checkin table
    query = """
        SELECT `employee`, `log_type`, `time`
        FROM `tabEmployee Checkin`
        WHERE `employee` = %s
        AND `time` BETWEEN %s AND %s
        ORDER BY `time` ASC
    """
    attendance_records = frappe.db.sql(query, (employee_name, start_datetime, end_datetime), as_dict=True)

    sessions = []
    total_working_seconds = 0
    current_session = {}

    for record in attendance_records:
        log_type = record["log_type"]
        log_time = record["time"]

        if log_type == "IN":
            if "in_time" in current_session and "out_time" not in current_session:
                sessions.append({
                    f"session {len(sessions) + 1}": {
                        "employee_name": employee_name,
                        "date": str(current_session["in_time"].date()),
                        "in_time": current_session["in_time"].strftime("%H:%M:%S"),
                        "out_time": "",
                        "working_hours": "0:00:00"
                    }
                })

            current_session = {"in_time": log_time}

        elif log_type == "OUT":
            if "in_time" not in current_session:
                sessions.append({
                    f"session {len(sessions) + 1}": {
                        "employee_name": employee_name,
                        "date": str(log_time.date()),
                        "in_time": "",
                        "out_time": log_time.strftime("%H:%M:%S"),
                        "working_hours": "0:00:00"
                    }
                })
            else:
                in_time = current_session["in_time"]
                out_time = log_time
                working_seconds = (out_time - in_time).total_seconds()
                total_working_seconds += working_seconds

                working_hours = f"{int(working_seconds // 3600)}:{str(int((working_seconds % 3600) // 60)).zfill(2)}:{str(int(working_seconds % 60)).zfill(2)}"

                sessions.append({
                    f"session {len(sessions) + 1}": {
                        "employee_name": employee_name,
                        "date": str(in_time.date()),
                        "in_time": in_time.strftime("%H:%M:%S"),
                        "out_time": out_time.strftime("%H:%M:%S"),
                        "working_hours": working_hours
                    }
                })
                current_session = {}  

    if "in_time" in current_session:
        sessions.append({
            f"session {len(sessions) + 1}": {
                "employee_name": employee_name,
                "date": str(current_session["in_time"].date()),
                "in_time": current_session["in_time"].strftime("%H:%M:%S"),
                "out_time": "",
                "working_hours": "0:00:00"
            }
        })

    # Convert total working seconds to hours:minutes:seconds format
    total_hours = int(total_working_seconds // 3600)
    total_minutes = int((total_working_seconds % 3600) // 60)
    total_seconds = int(total_working_seconds % 60)
    
    total_working_hours = f"{total_hours}:{str(total_minutes).zfill(2)}:{str(total_seconds).zfill(2)}"

    # Construct the final response JSON with labeled session records and total working hours in 'hours:minutes' format
    response = {
        "attendance_sessions": sessions,  # Nested session data with labeled sessions
        "working_hours": total_working_hours # Total working hours for the day
    }

    return response

# Recursive Function to Get Multi-Level Reportees
def get_all_reportees_api(employee_name, current_date):
    reportees = frappe.db.sql("""
        SELECT `employee`
        FROM `tabEmployee`
        WHERE `reports_to` = %s AND `status` = 'Active'
    """, (employee_name,), as_dict=True)

    all_reportees = []
    for reportee in reportees:
        reportee_data = {
            "employee": reportee["employee"],
            "reportee_attendance": get_main_attendance(reportee["employee"], date = current_date),
        }
        all_reportees.append(reportee_data)

    return {"current_date": current_date, "report_names": all_reportees, }

def get_w_m_average(employee_name, current_date):
    week_data = get_weekly_average(employee_name, current_date)
    month_data = get_monthly_average(employee_name, current_date)
    return {"week_data": week_data, "month_data": month_data}

def get_weekly_average(employee_name, current_date):
    # Convert string date to datetime object
    current_date = getdate(current_date)

    total_seconds = 0
    valid_days = 0  # Track number of valid weekdays (Mon-Sat)

    # Iterate over days from Monday to (Current Day - 1)
    for days_ago in range(1, current_date.weekday() + 1):  
        past_date = add_days(current_date, -days_ago)

        # Fetch attendance data for the day
        attendance = get_attendance(employee_name, str(past_date))
        if attendance.get("error") or attendance["working_hours"] == "0:00:00":
            continue  # Skip if no attendance data or working hours are 0

        working_hours = attendance["working_hours"]
        hours, minutes, seconds = map(int, working_hours.split(":"))
        daily_seconds = (hours * 3600) + (minutes * 60) + seconds

        total_seconds += daily_seconds
        valid_days += 1

    # If no valid days found, return 0
    if valid_days == 0:
        return {"error": "No working days found for weekly average calculation."}

    # Calculate the average in seconds
    avg_seconds = total_seconds // valid_days  
    avg_hours = avg_seconds // 3600
    avg_minutes = (avg_seconds % 3600) // 60

    # Format output
    avg_hh_mm = f"{avg_hours}.{str(avg_minutes).zfill(2)}"

    return {
        "weekly_avg_hh_mm": avg_hh_mm,  
        "days_considered": valid_days
    }

def get_monthly_average(employee_name, current_date):
    current_date = getdate(current_date)  # Convert string date to datetime object
    
    # Get the first of the current and next months
    first_day_of_current_month = current_date.replace(day=1)
    first_day_of_next_month = add_months(current_date.replace(day=1), 1)
    
    total_seconds = 0
    valid_days = 0  # Track number of valid working days
    
    # Fetch all valid dates with check-in data
    query = """
        SELECT DISTINCT DATE(`time`) as work_date
        FROM `tabEmployee Checkin`
        WHERE `employee` = %s
        AND `time` BETWEEN %s AND %s
    """
    valid_dates = frappe.db.sql(query, (employee_name, first_day_of_current_month, first_day_of_next_month), as_dict=True)


    for record in valid_dates:
        work_date = record["work_date"]
        
        # Fetch attendance data for the date
        attendance = get_attendance(employee_name, str(work_date))
        if attendance.get("error"):  
            continue  # Skip if no attendance data
        
        working_hours = attendance["working_hours"]
        hours, minutes, seconds = map(int, working_hours.split(":"))
        daily_seconds = (hours * 3600) + (minutes * 60) + seconds

        total_seconds += daily_seconds
        valid_days += 1

    # If no valid days found, return an error
    if valid_days == 0:
        return {"error": "No working days found for monthly average calculation."}

    # Calculate the average in seconds
    avg_seconds = total_seconds // valid_days  
    avg_hours = avg_seconds // 3600
    avg_minutes = (avg_seconds % 3600) // 60

    # Format output
    avg_hh_mm = f"{avg_hours}.{str(avg_minutes).zfill(2)}"

    return {
        "monthly_avg_hh_mm": avg_hh_mm,
        "days_considered": valid_days,
        "month": formatdate(first_day_of_current_month, "MMMM YYYY")  # Format as "March 2024"
    }
