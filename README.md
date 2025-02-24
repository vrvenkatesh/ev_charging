Our mission
Our mission is to revolutionize the electric vehicle charging experience through data. We strive to create a seamless charging experience that maximizes convenience and minimizes stress for EV drivers everywhere.

By harnessing the power of predictive analytics and real-time data processing, we aim to solve one of the biggest pain points for electric vehicle adoption - finding available chargers when and where you need them. Our availability forecasting model provides EV drivers with the ability to plan ahead, reducing range anxiety and eliminating wasted time idling at charging stations.

Problem
The electric vehicle (EV) revolution is accelerating at an incredible pace, but it’s facing major speed bumps - the charging station availability crisis. Finding available EV chargers is the fastest growing problem for EV owners, especially the +800k drivers in California where the rate of new vehicles doubles that of new chargers. Drivers can use existing charging apps to tell them a local spot is available, but arrive frustrated to find that the spot has been taken during their drive over. Should they wait for one to open up or try another location? Would tomorrow at the same time be better or worse? Unfortunately there are no charging apps that tell drivers when a spot will be available in the future, until now.

We introduce Charge Buddy - the first ever data driven approach to planning your next charging session. Charge Buddy eliminates the hassle of guessing by accurately predicting when chargers will be available before it happens, so drivers can spend less time waiting and more time enjoying their EVs. Additionally, Charge Buddy allows for user preferences. With California grid data, Charge buddy can find the lowest prices and high renewable energy supply, so EV owners can choose to get affordable, green charging sessions without the crowds!

Data
To help California EV owners find when to charge their cars, we explored many data sets. Our research and exploratory data analysis found that the day of week, time of day, and weather conditions play a big role in when drivers charge their cars. Additionally, CAISO, the California Energy Grid Operator, forecasts periods of high demand, which correlates well with charger use. For these reasons, we use grid, weather, and time data to train our models and predict EV charger availability in California.

Feature - Grid: The CAISO OASIS data portal provided energy demand forecasts in addition to renewable energy supply
Feature - Time: Month, day of week, and hour of the day were used
Feature - Weather: Meteostat and weather.gov data were used for historical and forecasted weather, respectively.
Outcome - Availabilty: the Adaptive Charging Network (ACN) dataset. It contains 4 years of electric vehicle charging history from 3 locations in Northern and Southern California. This data set provides us with typical charging patterns each hour over the course of the year. 
Model
We evaluated 3 models for the regression task of predicting charger availability at a site: Linear, Gradient-boosted Trees, and Long Short Term Memory. After performing an 80:20 train test split, we used hyperparameter tuning and cross validation to get the best results. The best performing model was the Gradient-boosted Trees model. The trained XGBoost model was deployed to our web application.

Evaluation
We evaluated our models using Root-Mean-Squared-Error (RMSE), the coefficient of determination (R2), and inference time as a proxy for app latency. Our baseline model was linear regression which yielded an RMSE of 0.193, R2 score of 0.53, and performed inference in 0.022 sec. The tuned LSTM model had an RMSE of 0.102, R2 of 0.872, and an inference time of 0.885 seconds. The best model was the XGBoost tree model, which yielded a RMSE of 0.101, goodness of fit of 0.875, and an inference time of 0.018 seconds.

We chose XGBoost because it had the best blend of low error and speed.

Key Learnings & Impact
The charger availability crisis has many stakeholders. Governments, grid operators, EV salespeople, charger manufacturers and charging station owners all need a solution to the high demand for chargers. And while it may not seem like it, Charge Buddy actually helps all of these stakeholders. That's because the solution to the charger availability crisis is not to build more chargers to meet demand, but to flatten the demand curve to meet supply. So while we focused on EV owners as our target users, Charge Buddy is changing the behavior of the fleet, pushing individuals to charge during off-peak hours with the promise of convenience in a way that price sensitivity cannot. We believe Charge Buddy can change user behavior resulting in an overall increase in EV charger uptime, limit energy demand peaks on the grid, and create satisfied EV owners that will rave about adoption to their friends and family members.

Acknowledgements
We would like to thank Puya, Kira, and our TAs for their guidance and support. Without them, this project would not be possible.
