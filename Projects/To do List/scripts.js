
document.getElementById('add-task').addEventListener('click', function() {
    let taskInput = document.getElementById('task-input');
    let taskList = document.getElementById('task-list');
    
    if(taskInput.value.trim() !== "") {
        addTaskToList(taskInput.value);
        taskInput.value = "";
        saveTasksToLocalStorage();
    }
});

document.getElementById('task-list').addEventListener('click', function(e) {
    if(e.target.classList.contains('delete-btn')) {
        e.target.parentElement.remove();
        saveTasksToLocalStorage();
    }
});

function addTaskToList(task) {
    let taskList = document.getElementById('task-list');
    let newTask = document.createElement('li');
    newTask.innerHTML = `${task} <span class="delete-btn">X</span>`;
    taskList.appendChild(newTask);
}

function saveTasksToLocalStorage() {
    let tasks = [];
    let taskListItems = document.querySelectorAll('#task-list li');
    taskListItems.forEach(item => {
        tasks.push(item.innerText.substring(0, item.innerText.length - 2)); // Exclude the 'X' delete button text
    });
    localStorage.setItem('tasks', JSON.stringify(tasks));
}

function loadTasksFromLocalStorage() {
    let tasks = JSON.parse(localStorage.getItem('tasks'));
    if(tasks && tasks.length > 0) {
        tasks.forEach(task => {
            addTaskToList(task);
        });
    }
}

// Load tasks from local storage when the page loads
loadTasksFromLocalStorage();
