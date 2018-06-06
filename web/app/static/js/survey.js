Survey.defaultBootstrapCss.navigationButton = "btn btn-green";
Survey.defaultBootstrapCss.rating.item = "btn btn-outline-secondary my-rating";
Survey.Survey.cssType = "bootstrap";


var json = {
 showProgressBar: "top",
 pages: [
  {
   name: "page1",
   elements: [
    {
     type: "matrix",
     name: "question4",
     title: "Are you aware that your location is tracked at all times by multiple applications installed on your smartphone?",
     columns: [
      {
       value: "yes",
       text: "Yes"
      },
      {
       value: "no",
       text: "No"
      }
     ],
     rows: [
      {
       value: "before",
       text: "Before the study"
      },
      {
       value: "after",
       text: "After the study"
      }
     ]
    },
    {
     type: "matrix",
     name: "question2",
     title: "Do you know that your location data is shared to different entities, including apps and third parties such as advertisers?",
     columns: [
      {
       value: "yes",
       text: "Yes"
      },
      {
       value: "no",
       text: "No"
      }
     ],
     rows: [
      {
       value: "before",
       text: "Before the study"
      },
      {
       value: "after",
       text: "After the study"
      }
     ]
    },
    {
     type: "matrix",
     name: "question1",
     title: "Do you know that your location data and the places you visit reveal personal information, including interests, about yourself?",
     columns: [
      {
       value: "yes",
       text: "Yes"
      },
      {
       value: "no",
       text: "No"
      }
     ],
     rows: [
      {
       value: "before",
       text: "Before the study"
      },
      {
       value: "after",
       text: "After the study"
      }
     ]
    },
    {
     type: "matrix",
     name: "question3",
     title: "Do you know that your location data, the places you visit, and personal information are used to provide tailored advertisement based on your interests extracted from the places you visited?",
     columns: [
      {
       value: "yes",
       text: "Yes"
      },
      {
       value: "no",
       text: "No"
      }
     ],
     rows: [
      {
       value: "before",
       text: "Before the study"
      },
      {
       value: "after",
       text: "After the study"
      }
     ]
    },
    {
     type: "rating",
     name: "question5",
     title: "Would you consider the information we have shown you during the study (extracted from the places you visited) to be private or personal in nature?",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    }
   ],
   title: "Location data and personal information awareness"
  },
  {
   name: "page2",
   elements: [
    {
     type: "rating",
     name: "question6",
     title: "How important is it to you to prevent applications from collecting personal information?",
     rateValues: [
      {
       value: "1",
       text: "Not important"
      },
      {
       value: "2",
       text: "Somewhat important"
      },
      {
       value: "3",
       text: "Very important"
      }
     ]
    },
    {
     type: "rating",
     name: "question7",
     title: "Do you generally give access to the always location services of your phone to the different applications that request it?",
     rateValues: [
      {
       value: 2,
       text: "Always"
      },
      {
       value: 3,
       text: "For applications I trust"
      },
      {
       value: 4,
       text: "Never"
      }
     ]
    },
    {
     type: "rating",
     name: "question8",
     title: "Do you generally give access to the when-in-use location services of your phone to the different applications that request it?",
     rateValues: [
      {
       value: 2,
       text: "Always"
      },
      {
       value: 3,
       text: "For applications I trust"
      },
      {
       value: 4,
       text: "Never"
      }
     ]
    }
   ],
   title: "Allowing applications to collect location data"
  },
  {
   name: "page3",
   elements: [
    {
     type: "rating",
     name: "question9",
     title: "Applications and services you have installed on your phone can collect some location information about you even if you have not granted them access to location services.",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    },
    {
     type: "rating",
     name: "question10",
     title: "Applications and services installed on your mobile phone can collect your location data just from the websites you visit from your phone.",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    },
    {
     type: "rating",
     name: "question11",
     title: "Your phone mobile carrier can collect your location data when you connect to their 3G/4G network.",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    },
    {
     type: "rating",
     name: "question12",
     title: "Places that you visit (such as malls or shops) can record your presence and match it against your previous visits.",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    }
   ],
   title: "Location data collection and third parties"
  },
  {
   name: "page4",
   elements: [
    {
     type: "rating",
     name: "question13",
     title: "You feel that you own and are in control of the data that you share with websites, applications and services that you use or visit.",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    },
    {
     type: "rating",
     name: "question14",
     title: "Users and consumers have lost all control over how personal information is collected and used by companies.",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    },
    {
     type: "rating",
     name: "question15",
     title: "Most businesses handle the personal information they collect about users and consumers in a proper and confidential way.",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    },
    {
     type: "rating",
     name: "question16",
     title: "Existing laws and organizational practices provide a reasonable level of protection for consumer privacy today.",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    },
    {
     type: "matrix",
     name: "question17",
     title: "What makes you trust an application with the personal data that you share? Rate the items according to whether they increase or decrease your trust of the application.",
     columns: [
      {
       value: "col1",
       text: "Increases my trust"
      },
      {
       value: "col2",
       text: "Neither increases or decreases my trust"
      },
      {
       value: "col3",
       text: "Decreases my trust"
      }
     ],
     rows: [
      {
       value: "1",
       text: "Their privacy policy statement"
      },
      {
       value: "2",
       text: "Regulatory laws"
      },
      {
       value: "3",
       text: "The fact that they are free"
      },
      {
       value: "4",
       text: "The fact that they are paid"
      },
      {
       value: "5",
       text: "Their popularity/rating with other users"
      },
      {
       value: "6",
       text: "Current events or data leak scandals"
      }
     ]
    },
    {
     type: "matrix",
     name: "question18",
     title: "Sharing any information with a service can affect your privacy as well as that other people around you. Rate how much you value privacy in the following contexts.",
     columns: [
      {
       value: "col1",
       text: "Not important"
      },
      {
       value: "col2",
       text: "Somewhat important"
      },
      {
       value: "col3",
       text: "Very important"
      }
     ],
     rows: [
      {
       value: "1",
       text: "Information that only relates to me"
      },
      {
       value: "2",
       text: "Information that only relates to other people that are close to you or under your responsibility"
      },
      {
       value: "3",
       text: "Information that only relates to other people that you don’t know"
      }
     ]
    }
   ],
   title: "User trust and privacy"
  },
  {
   name: "page5",
   elements: [
    {
     type: "rating",
     name: "question19",
     title: "When you use a free application or service, one that is mostly supported by advertising, do you have more privacy rights than a paid application or service.",
     rateValues: [
      {
       value: "1",
       text: "I have more privacy rights"
      },
      {
       value: "2",
       text: "I have the same privacy rights"
      },
      {
       value: "3",
       text: "I have less privacy rights"
      },
      {
       value: "item1",
       text: "I don't know"
      }
     ]
    },
    {
     type: "rating",
     name: "question20",
     title: "A service that collects location data of thousands or millions of individuals better protects your privacy and anonymity.",
     rateValues: [
      {
       value: "1",
       text: "Strongly disagree"
      },
      {
       value: "2",
       text: "Neither agree nor disagree"
      },
      {
       value: "3",
       text: "Strongly agree"
      }
     ]
    },
    {
     type: "rating",
     name: "question21",
     title: "How necessary is it for companies to have access to the location data of individuals that use their service?",
     rateValues: [
      {
       value: "1",
       text: "Not necessary"
      },
      {
       value: "2",
       text: "Somewhat necessary"
      },
      {
       value: "3",
       text: "Very necessary"
      }
     ]
    },
    {
     type: "rating",
     name: "question22",
     title: "Sharing your location data leads to more personalized services and tailored recommendations. With this in mind, how important is it to share your location data?",
     rateValues: [
      {
       value: "1",
       text: "Not important at all"
      },
      {
       value: "2",
       text: "Somewhat important"
      },
      {
       value: "3",
       text: "Very important"
      }
     ]
    },
    {
     type: "rating",
     name: "question23",
     title: " In addition to services, sharing your location data also leads to ads and sponsored content tailored to your interests. With this in mind, how important is it to share your location data?",
     rateValues: [
      {
       value: "1",
       text: "Not important at all"
      },
      {
       value: "2",
       text: "Somewhat important"
      },
      {
       value: "3",
       text: "Very important"
      }
     ]
    },
    {
     type: "radiogroup",
     name: "question24",
     title: "Would you be willing to pay a fee in exchange for complete privacy and  anonymity when you share your location?",
     choices: [
      {
       value: "item1",
       text: "Yes, I would pay one fixed fee"
      },
      {
       value: "item2",
       text: "Yes, I would pay a recurring monthly fee"
      },
      {
       value: "item3",
       text: "No, I would rather use the free service"
      }
     ]
    }
   ],
   title: "Free applications & services"
  },
  {
   name: "page6",
   elements: [
    {
     type: "rating",
     name: "question25",
     title: "In general, do you find ads and sponsored content useful?",
     minRateDescription: "Not useful at all",
     maxRateDescription: "Very useful"
    },
    {
     type: "rating",
     name: "question26",
     title: "In general, do you find ads and sponsored content relevant to your interests?",
     minRateDescription: "Not relevant at all ",
     maxRateDescription: " Very relevant"
    },
    {
     type: "rating",
     name: "question27",
     title: "Do you think that ads and sponsored content based on the places you visited useful?",
     minRateDescription: "Not useful at all",
     maxRateDescription: "Very useful"
    },
    {
     type: "rating",
     name: "question28",
     title: "Do you frequently click on the ads or sponsored content served in the websites, application or services that you use?",
     minRateDescription: "Never",
     maxRateDescription: "Always"
    }
   ],
   title: "Attitudes toward ads and sponsored content"
  }
 ]
};

window.survey = new Survey.Model(json);


survey.onComplete.add(function(result) {
    document.querySelector('#surveyResult').innerHTML = "result: " + JSON.stringify(result.data);
});


$("#surveyElement").Survey({ 
    model: survey 
});
