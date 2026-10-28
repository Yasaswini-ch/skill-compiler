---
name: trip-day-planner
description: Work out the timeline from landing to dinner on the first day of a trip.
---

# Trip day planner

1. Extract the landing time from the input. Write it in 24-hour HH:MM format.
2. Add 45 minutes to the landing time for baggage and customs. The result is the time you leave the airport.
3. Extract the taxi time to the hotel and convert it to minutes. Add it to the time you leave the airport. The result is the hotel arrival time.
4. Hotel check-in opens at 15:00. If the hotel arrival time is earlier than 15:00, the check-in time is 15:00. Otherwise the check-in time equals the hotel arrival time.
5. Dinner is at 19:30. Compute the number of whole minutes from the check-in time to 19:30.
6. Output exactly 4 lines and nothing else, in this format:

   Leave airport: HH:MM
   Hotel arrival: HH:MM
   Check-in: HH:MM
   Free minutes before dinner: N
