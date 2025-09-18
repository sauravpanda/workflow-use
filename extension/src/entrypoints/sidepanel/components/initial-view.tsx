import React, { useState } from "react";
import { useWorkflow } from "../context/workflow-provider";
import { Button } from "@/components/ui/button"; // Reverted to alias path

export const InitialView: React.FC = () => {
  const { startRecording } = useWorkflow();
  const [showTemplates, setShowTemplates] = useState(false);

  const workflowTemplates = [
    {
      name: "E-commerce Product Research",
      description: "Navigate product pages and extract prices, reviews, specifications",
      steps: "Search → Product page → Extract pricing & reviews",
      icon: "🛒"
    },
    {
      name: "Job Listings Scraper", 
      description: "Browse job boards and extract job details, requirements, salaries",
      steps: "Search jobs → Job listings → Extract job details",
      icon: "💼"
    },
    {
      name: "Travel Booking Flow",
      description: "Search flights/hotels and extract prices, availability, options",
      steps: "Search → Results → Extract pricing & options", 
      icon: "✈️"
    },
    {
      name: "Lead Generation",
      description: "Navigate directories and extract contact information",
      steps: "Directory → Company pages → Extract contact info",
      icon: "📊"
    },
    {
      name: "Social Media Monitoring",
      description: "Browse social platforms and extract posts, metrics, engagement",
      steps: "Profile/hashtag → Posts → Extract content & metrics",
      icon: "📱"
    },
    {
      name: "Custom Workflow",
      description: "Record any workflow with manual actions and AI extraction",
      steps: "Start recording and add AI extraction when needed",
      icon: "🎯"
    }
  ];

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="flex-grow flex flex-col items-center justify-center space-y-6 p-4">
        <div className="text-center space-y-2">
          <h2 className="text-xl font-semibold text-gray-900">Create a Workflow</h2>
          <p className="text-sm text-gray-600 max-w-md">
            Record your actions and add AI extraction steps to automatically gather data from web pages
          </p>
        </div>

        <div className="space-y-3 w-full max-w-md">
          <Button 
            onClick={startRecording} 
            className="w-full h-12 text-base font-medium"
            size="lg"
          >
            🔴 Start Recording Workflow
          </Button>
          
          <Button 
            variant="outline" 
            onClick={() => setShowTemplates(!showTemplates)}
            className="w-full text-sm"
          >
            📋 View Workflow Templates
          </Button>
        </div>

        {showTemplates && (
          <div className="w-full max-w-2xl space-y-3">
            <h3 className="text-sm font-medium text-center text-gray-900">Workflow Templates</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-64 overflow-y-auto">
              {workflowTemplates.map((template, index) => (
                <div 
                  key={index}
                  className="border border-gray-200 rounded-lg p-3 hover:bg-gray-50 hover:border-gray-300 cursor-pointer transition-all"
                  onClick={() => {
                    setShowTemplates(false);
                    startRecording();
                  }}
                >
                  <div className="flex items-start space-x-3">
                    <span className="text-2xl">{template.icon}</span>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-medium text-gray-900 truncate">{template.name}</h4>
                      <p className="text-xs text-gray-600 mt-1">{template.description}</p>
                      <div className="text-xs text-blue-600 mt-2 font-medium">
                        {template.steps}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="text-xs text-center text-gray-600 bg-blue-50 p-3 rounded border border-blue-200">
              💡 <strong>Pro tip:</strong> Add AI extraction steps during recording to automatically capture data from the final page. 
              The AI can extract structured information like prices, contact details, or any specific data you describe.
            </div>
          </div>
        )}

        <div className="text-center space-y-2 max-w-md">
          <h3 className="text-sm font-medium text-gray-900">How it works:</h3>
          <div className="text-xs text-gray-600 space-y-1">
            <div className="flex items-center space-x-2">
              <span>1️⃣</span>
              <span>Record your actions (clicks, inputs, navigation)</span>
            </div>
            <div className="flex items-center space-x-2">
              <span>2️⃣</span>
              <span>Add AI extraction steps when you want to gather data</span>
            </div>
            <div className="flex items-center space-x-2">
              <span>3️⃣</span>
              <span>Save and run your workflow to automate the process</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
