import frappe
from frappe.utils import add_days, get_datetime, today, getdate, add_months, formatdate
import json
import time
from datetime import timedelta
from collections import defaultdict

# -------------------------------------------------------------------------
# Cache implementation with TTL and manual invalidation
# -------------------------------------------------------------------------
_cache = {}
_cache_timestamp = {}
CACHE_TTL = 300  # 5 minutes in seconds

def cache_get(key):
    """Get a value from cache if it exists and is not expired"""
    if key in _cache and key in _cache_timestamp:
        if time.time() - _cache_timestamp[key] < CACHE_TTL:
            return _cache[key]
    return None

def cache_set(key, value):
    """Set a value in cache with current timestamp"""
    _cache[key] = value
    _cache_timestamp[key] = time.time()
    return value

def cache_clear(prefix=None):
    """Clear all cache or cache with specific prefix"""
    global _cache, _cache_timestamp
    if prefix is None:
        _cache = {}
        _cache_timestamp = {}
    else:
        keys_to_delete = [k for k in _cache.keys() if k.startswith(prefix)]
        for key in keys_to_delete:
            if key in _cache:
                del _cache[key]
            if key in _cache_timestamp:
                del _cache_timestamp[key]

# -------------------------------------------------------------------------
# Basic API Functions
# -------------------------------------------------------------------------
@frappe.whitelist()
def get_date():
    """Return current date"""
    return frappe.utils.today()

@frappe.whitelist()
def get_user_details(email=None):
    """Get user details from email"""
    if not email:
        return {"error": "Email parameter is required."}
    
    # Special case for admin users
    if email in ["Administrator", "silerp@softlandindia.co.in"]:
        return {
            "full_name": "MURALY G",
            "email": "silerp@softlandindia.co.in"
        }
    
    # Check cache first
    cache_key = f"user_details:{email}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
    
    try:
        # Query the database
        employee = frappe.db.get_value(
            "Employee", 
            {"user_id": email}, 
            ["employee", "user_id"], 
            as_dict=True
        )
        
        if not employee:
            return {"error": "User not found."}
            
        result = {
            "full_name": employee.employee,
            "email": employee.user_id
        }
        
        # Cache the result
        return cache_set(cache_key, result)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Unexpected Error in get_user_details")
        return {"error": str(e)}

# -------------------------------------------------------------------------
# Attendance Data Functions
# -------------------------------------------------------------------------
def get_attendance_records(employee_name, date_str):
    """Get attendance records for an employee on a specific date"""
    cache_key = f"attendance:{employee_name}:{date_str}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
    
    start_datetime = get_datetime(date_str + " 00:00:00")
    end_datetime = get_datetime(date_str + " 23:59:59")

    query = """
        SELECT `log_type`, `time`
        FROM `tabEmployee Checkin`
        WHERE `employee` = %s
        AND `time` BETWEEN %s AND %s
        ORDER BY `time` ASC
    """
    
    result = frappe.db.sql(query, (employee_name, start_datetime, end_datetime), as_dict=True)
    return cache_set(cache_key, result)

def get_employee_details(employee_name):
    """Get employee details"""
    cache_key = f"employee:{employee_name}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
    
    result = frappe.db.get_value(
        "Employee", 
        {"employee": employee_name}, 
        ["department", "custom_team", "reports_to"], 
        as_dict=True
    ) or {}
    
    return cache_set(cache_key, result)

def process_attendance_records(employee_name, attendance_records):
    """Process attendance records to get sessions and total working hours"""
    sessions = []
    total_working_seconds = 0
    current_session = {}
    first_checkin = None
    last_logout = None

    for record in attendance_records:
        log_type = record["log_type"]
        log_time = record["time"]

        if log_type == "IN":
            if not first_checkin:
                first_checkin = log_time.strftime("%H:%M:%S")
                
            if "in_time" in current_session and "out_time" not in current_session:
                # Incomplete previous session
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
            last_logout = log_time.strftime("%H:%M:%S")
            
            if "in_time" not in current_session:
                # Orphaned check-out
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
                # Complete session
                in_time = current_session["in_time"]
                out_time = log_time
                working_seconds = (out_time - in_time).total_seconds()
                total_working_seconds += working_seconds

                working_hours = format_seconds_to_time(working_seconds)

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

    # Handle incomplete final session
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

    total_working_hours = format_seconds_to_time(total_working_seconds)
    
    return sessions, total_working_hours, total_working_seconds, first_checkin, last_logout

def format_seconds_to_time(seconds):
    """Format seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours}:{str(minutes).zfill(2)}:{str(seconds).zfill(2)}"

# -------------------------------------------------------------------------
# Main Attendance API
# -------------------------------------------------------------------------
@frappe.whitelist()
def get_main_attendance(employee_name, date):
    """Get attendance summary for an employee"""
    cache_key = f"main_attendance:{employee_name}:{date}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
    
    # Fetch attendance records
    attendance_records = get_attendance_records(employee_name, date)
    
    # Process records
    _, total_working_hours, _, first_checkin, last_logout = process_attendance_records(
        employee_name, attendance_records
    )

    # Employee details
    employee_details = get_employee_details(employee_name)
    
    # Get report hierarchy using a non-recursive approach
    report_hierarchy = get_all_reportees_api(employee_name, date)
    
    # Calculate weekly and monthly averages
    w_m_average = get_w_m_average(employee_name, date)

    result = {
        "employee_name": employee_name,
        "first_checkin": first_checkin if first_checkin else "-",
        "last_logout": last_logout if last_logout else "-",
        "department": employee_details.get("department", "-") if employee_details else "-",
        "custom_team": employee_details.get("custom_team", "-") if employee_details else "-",
        "total_working_hours": total_working_hours,
        "w_m_average": w_m_average,
        "report_hierarchy": report_hierarchy
    }
    
    return cache_set(cache_key, result)

@frappe.whitelist()
def get_attendance(employee_name, date):
    """Get detailed attendance sessions for an employee"""
    cache_key = f"attendance_details:{employee_name}:{date}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
    
    # Get attendance records
    attendance_records = get_attendance_records(employee_name, date)
    
    # Process records to get sessions and working hours
    sessions, total_working_hours, _, _, _ = process_attendance_records(
        employee_name, attendance_records
    )

    # Construct the final response JSON
    result = {
        "attendance_sessions": sessions,
        "working_hours": total_working_hours
    }
    
    return cache_set(cache_key, result)

# -------------------------------------------------------------------------
# Reporting Hierarchy Functions
# -------------------------------------------------------------------------
def get_reportees_map():
    """Get all employee reporting relationships in one query"""
    cache_key = "all_reporting_relationships"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
    
    query = """
        SELECT employee, reports_to
        FROM `tabEmployee`
        WHERE status = 'Active' AND reports_to IS NOT NULL
    """
    
    results = frappe.db.sql(query, as_dict=True)
    
    # Build reporting hierarchy as a directed graph
    hierarchy = defaultdict(list)
    for row in results:
        if row['reports_to']:
            hierarchy[row['reports_to']].append(row['employee'])
    
    return cache_set(cache_key, dict(hierarchy))

def get_all_reportees_api(employee_name, current_date):
    """Get all reportees for an employee in a non-recursive way"""
    cache_key = f"reportees:{employee_name}:{current_date}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
    
    # Get all reporting relationships
    all_reports = get_reportees_map()
    
    # Use queue to process all reportees without recursion
    result_reportees = []
    queue = [(employee_name, None)]  # (employee, reports_to)
    processed = set()
    direct_reports = []
    
    # First level reportees are handled separately
    if employee_name in all_reports:
        direct_reports = all_reports[employee_name]
        for reportee in direct_reports:
            queue.append((reportee, employee_name))
    
    # Process direct reports first for a cleaner hierarchy
    for reportee in direct_reports:
        if reportee in processed:
            continue
            
        processed.add(reportee)
        
        # Get attendance for the reportee
        reportee_attendance = get_main_attendance(reportee, current_date)
        
        # Add reportee to the result
        reportee_data = {
            "employee": reportee,
            "reportee_attendance": reportee_attendance,
            # We'll add sub-reportees later as needed
        }
        
        result_reportees.append(reportee_data)
    
    result = {
        "current_date": current_date, 
        "report_names": result_reportees
    }
    
    return cache_set(cache_key, result)

# -------------------------------------------------------------------------
# Average Calculation Functions
# -------------------------------------------------------------------------
def get_w_m_average(employee_name, current_date):
    """Get weekly and monthly averages"""
    cache_key = f"w_m_average:{employee_name}:{current_date}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
    
    # Calculate averages
    week_data = get_weekly_average(employee_name, current_date)
    month_data = get_monthly_average(employee_name, current_date)
    
    result = {"week_data": week_data, "month_data": month_data}
    return cache_set(cache_key, result)

def get_weekly_average(employee_name, current_date):
    """Calculate weekly average working hours"""
    cache_key = f"weekly_avg:{employee_name}:{current_date}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
        
    current_date = getdate(current_date)
    
    # Get the start of the week (Monday)
    week_start = add_days(current_date, -current_date.weekday())
    
    # Get all check-ins/check-outs for the week in one query
    query = """
        SELECT DATE(`time`) as work_date, `log_type`, `time`
        FROM `tabEmployee Checkin`
        WHERE `employee` = %s
        AND DATE(`time`) >= %s
        AND DATE(`time`) <= %s
        ORDER BY `time` ASC
    """
    
    week_records = frappe.db.sql(
        query, 
        (
            employee_name, 
            week_start,
            current_date
        ), 
        as_dict=True
    )
    
    # Group records by date
    daily_records = {}
    for record in week_records:
        date_str = str(record["work_date"])
        if date_str not in daily_records:
            daily_records[date_str] = []
        daily_records[date_str].append(record)
    
    # Calculate working hours for each day
    total_seconds = 0
    valid_days = 0
    
    for date_str, records in daily_records.items():
        if date_str == str(current_date):
            continue  # Skip current day
            
        # Calculate working hours for this day
        day_seconds = 0
        current_session = {}
        
        for record in records:
            log_type = record["log_type"]
            log_time = record["time"]
            
            if log_type == "IN":
                current_session["in_time"] = log_time
            elif log_type == "OUT" and "in_time" in current_session:
                working_seconds = (log_time - current_session["in_time"]).total_seconds()
                day_seconds += working_seconds
                current_session = {}
        
        if day_seconds > 0:
            total_seconds += day_seconds
            valid_days += 1
    
    # Calculate average
    if valid_days == 0:
        result = {"weekly_avg_hh_mm": "0.00", "days_considered": 0}
    else:
        avg_seconds = total_seconds // valid_days
        avg_hours = int(avg_seconds // 3600)
        avg_minutes = int((avg_seconds % 3600) // 60)
        
        # Format output
        avg_hh_mm = f"{avg_hours}.{str(avg_minutes).zfill(2)}"
        
        result = {
            "weekly_avg_hh_mm": avg_hh_mm,
            "days_considered": valid_days
        }
    
    return cache_set(cache_key, result)

def get_monthly_average(employee_name, current_date):
    """Calculate monthly average working hours"""
    cache_key = f"monthly_avg:{employee_name}:{current_date}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return cached_data
        
    current_date = getdate(current_date)
    
    # Get the first day of the current month
    first_day_of_current_month = current_date.replace(day=1)
    
    # Get all check-ins/check-outs for the month in one query
    query = """
        SELECT DATE(`time`) as work_date, `log_type`, `time`
        FROM `tabEmployee Checkin`
        WHERE `employee` = %s
        AND DATE(`time`) >= %s
        AND DATE(`time`) <= %s
        ORDER BY `time` ASC
    """
    
    month_records = frappe.db.sql(
        query, 
        (
            employee_name, 
            first_day_of_current_month,
            current_date
        ), 
        as_dict=True
    )
    
    # Group records by date
    daily_records = {}
    for record in month_records:
        date_str = str(record["work_date"])
        if date_str not in daily_records:
            daily_records[date_str] = []
        daily_records[date_str].append(record)
    
    # Calculate working hours for each day
    total_seconds = 0
    valid_days = 0
    
    for date_str, records in daily_records.items():
        if date_str == str(current_date):
            continue  # Skip current day
            
        # Calculate working hours for this day
        day_seconds = 0
        current_session = {}
        
        for record in records:
            log_type = record["log_type"]
            log_time = record["time"]
            
            if log_type == "IN":
                current_session["in_time"] = log_time
            elif log_type == "OUT" and "in_time" in current_session:
                working_seconds = (log_time - current_session["in_time"]).total_seconds()
                day_seconds += working_seconds
                current_session = {}
        
        if day_seconds > 0:
            total_seconds += day_seconds
            valid_days += 1
    
    # Calculate average
    if valid_days == 0:
        result = {
            "monthly_avg_hh_mm": "0.00", 
            "days_considered": 0,
            "month": formatdate(first_day_of_current_month, "MMMM YYYY")
        }
    else:
        avg_seconds = total_seconds // valid_days
        avg_hours = int(avg_seconds // 3600)
        avg_minutes = int((avg_seconds % 3600) // 60)
        
        # Format output
        avg_hh_mm = f"{avg_hours}.{str(avg_minutes).zfill(2)}"
        
        result = {
            "monthly_avg_hh_mm": avg_hh_mm,
            "days_considered": valid_days,
            "month": formatdate(first_day_of_current_month, "MMMM YYYY")
        }
    
    return cache_set(cache_key, result)

# Optional: Add this function if you need to manually clear cache
@frappe.whitelist()
def clear_attendance_cache(employee_name=None):
    """Clear attendance cache for a specific employee or all employees"""
    if employee_name:
        cache_clear(f"attendance:{employee_name}")
        cache_clear(f"main_attendance:{employee_name}")
        cache_clear(f"attendance_details:{employee_name}")
        cache_clear(f"weekly_avg:{employee_name}")
        cache_clear(f"monthly_avg:{employee_name}")
        cache_clear(f"w_m_average:{employee_name}")
        cache_clear(f"reportees:{employee_name}")
        return {"status": "success", "message": f"Cache cleared for employee {employee_name}"}
    else:
        cache_clear()
        return {"status": "success", "message": "All cache cleared"}
