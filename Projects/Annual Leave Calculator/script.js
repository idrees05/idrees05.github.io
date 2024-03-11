document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('calculate').addEventListener('click', calculateAnnualLeaveAndBankHolidays);
});

function calculateAnnualLeaveAndBankHolidays() {
    const fullTimeLeaveOptions = {
        '202.5': 202.5,
        '217.5': 217.5,
        '247.5': 247.5
    };
    const fullTimeHours = 37.5;
    const fullTimeBankHolidays = 60; // Full time bank holiday leave hours

    // Inputs for the first period
    const startDate1 = document.getElementById('start-date-1').value;
    const endDate1 = document.getElementById('end-date-1').value;
    const hoursWeek1 = parseFloat(document.getElementById('hours-week-1').value);

    // Inputs for the second period (if applicable)
    const startDate2 = document.getElementById('start-date-2').value;
    const endDate2 = document.getElementById('end-date-2').value;
    const hoursWeek2 = parseFloat(document.getElementById('hours-week-2').value);

    // Annual leave option selected
    const annualLeaveFullTime = fullTimeLeaveOptions[document.getElementById('full-time-leave').value];

    // Calculate total days for each period
    const totalDays1 = (new Date(endDate1) - new Date(startDate1)) / (1000 * 60 * 60 * 24) + 1;
    const totalDays2 = (new Date(endDate2) - new Date(startDate2)) / (1000 * 60 * 60 * 24) + 1;

    // Calculate weeks for each period
    const weeks1 = totalDays1 / 7;
    const weeks2 = totalDays2 / 7;

    // Calculate pro-rated annual leave for each period
    const leave1 = (hoursWeek1 / fullTimeHours) * annualLeaveFullTime * (weeks1 / 52);
    const leave2 = (hoursWeek2 / fullTimeHours) * annualLeaveFullTime * (weeks2 / 52);

    // Sum of pro-rated leaves for both periods
    const totalAnnualLeave = leave1 + leave2;

    // Calculate bank holiday entitlement for a full year based on the latest working hours
    // Assuming hoursWeek2 represents the new or current working hours
    const bankHolidayEntitlement = (hoursWeek2 / fullTimeHours) * fullTimeBankHolidays;

    // Display the results
    document.getElementById('result').innerText = `Total Annual Leave: ${totalAnnualLeave.toFixed(2)} hours. Bank Holiday Entitlement for a Full Year with Current/New Hours: ${bankHolidayEntitlement.toFixed(2)} hours.`;
}
