// MyAgent Web 前端逻辑

let pollingTimer = null;

// ——— 初始化 ———

document.addEventListener('DOMContentLoaded', () => {
    loadModels();
    refreshTasks();
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'Enter') {
            sendMessage();
        }
    });
});

// ——— 模型列表 ———

async function loadModels() {
    try {
        const resp = await fetch('/api/models');
        const models = await resp.json();
        const select = document.getElementById('model-select');
        select.innerHTML = models.map(m =>
            `<option value="${m.name}">${m.name} ${m.configured ? '' : '(未配置)'}</option>`
        ).join('');
    } catch (e) {
        console.error('加载模型列表失败:', e);
    }
}

// ——— 发送消息 ———

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    input.disabled = true;
    document.getElementById('send-btn').disabled = true;

    appendMessage('user', message);
    const loadingMsg = appendMessage('bot', '⏳ 正在处理...');

    try {
        const model = document.getElementById('model-select').value;
        const resp = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, model }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            loadingMsg.querySelector('.message-bubble').innerHTML =
                `<p style="color:#e74c3c;">❌ 提交失败: ${err.detail || '未知错误'}</p>`;
            input.disabled = false;
            document.getElementById('send-btn').disabled = false;
            return;
        }

        const data = await resp.json();
        loadingMsg.querySelector('.message-bubble').innerHTML =
            `<p>✅ 任务已提交 (ID: ${data.task_id})</p>
             <p>仿真正在后台运行，完成后会提醒你。</p>`;

        startPolling(data.task_id, loadingMsg);

    } catch (e) {
        loadingMsg.querySelector('.message-bubble').innerHTML =
            `<p style="color:#e74c3c;">❌ 网络错误: ${e.message}</p>`;
    }

    input.disabled = false;
    document.getElementById('send-btn').disabled = false;
    refreshTasks();
}

// ——— 消息管理 ———

function appendMessage(role, text) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `
        <div class="message-avatar">${role === 'user' ? '👤' : '🤖'}</div>
        <div class="message-bubble"><p>${text}</p></div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

// ——— 任务轮询 ———

function startPolling(taskId, messageEl) {
    if (pollingTimer) clearInterval(pollingTimer);

    pollingTimer = setInterval(async () => {
        try {
            const resp = await fetch(`/api/tasks/${taskId}`);
            const task = await resp.json();

            let statusText = `🔧 任务状态: ${task.status_text}`;
            if (task.progress_detail) {
                statusText += `\n${task.progress_detail}`;
            }
            messageEl.querySelector('.message-bubble').innerHTML =
                `<p>${statusText}</p>`;

            if (task.status === 'completed') {
                clearInterval(pollingTimer);
                pollingTimer = null;
                showCompletionMessage(task, messageEl);
                showNotification(task);
                refreshTasks();
            } else if (task.status === 'failed') {
                clearInterval(pollingTimer);
                pollingTimer = null;
                messageEl.querySelector('.message-bubble').innerHTML =
                    `<p style="color:#e74c3c;">❌ 任务失败: ${task.error || '未知错误'}</p>`;
                refreshTasks();
            }

        } catch (e) {
            console.error('轮询失败:', e);
        }
    }, 3000);
}

function showCompletionMessage(task, messageEl) {
    const summary = task.result_summary || {};
    let html = '<p>✅ 仿真完成!</p>';

    if (summary.max_stress !== undefined && summary.max_stress !== null) {
        html += `<p>📊 最大应力: ${summary.max_stress} MPa</p>`;
    }
    if (summary.max_displacement !== undefined && summary.max_displacement !== null) {
        html += `<p>📏 最大位移: ${summary.max_displacement} mm</p>`;
    }

    html += '<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;">';
    if (task.report_available) {
        html += `<a href="/download/${task.task_id}/report" class="btn-download" download>📥 下载报告</a>`;
    }
    if (task.result_images && task.result_images.length > 0) {
        task.result_images.forEach(img => {
            html += `<a href="/download/${task.task_id}/${img}" class="btn-download" download>🖼️ ${img}</a>`;
        });
    }
    html += '</div>';

    messageEl.querySelector('.message-bubble').innerHTML = html;
}

// ——— 完成提醒 ———

function showNotification(task) {
    document.getElementById('notification-title').textContent = '✅ 任务完成!';
    document.getElementById('notification-msg').textContent =
        '仿真已完成，可在右侧任务列表中查看和下载结果。';
    document.getElementById('notification').classList.remove('hidden');
}

function dismissNotification() {
    document.getElementById('notification').classList.add('hidden');
}

// ——— 任务列表 ———

async function refreshTasks() {
    try {
        const resp = await fetch('/api/tasks');
        const tasks = await resp.json();
        const container = document.getElementById('task-list');

        if (tasks.length === 0) {
            container.innerHTML = '<div class="task-empty">暂无任务</div>';
            return;
        }

        container.innerHTML = tasks.map(t => {
            const statusClass = {
                'submitted': 'status-pending',
                'generating': 'status-pending',
                'executing': 'status-pending',
                'extracting': 'status-pending',
                'completed': 'status-done',
                'failed': 'status-failed',
            }[t.status] || 'status-pending';

            const statusIcon = {
                'submitted': '📨',
                'generating': '🔧',
                'executing': '⚙️',
                'extracting': '📊',
                'completed': '✅',
                'failed': '❌',
            }[t.status] || '⏳';

            let downloadBtns = '';
            if (t.report_available) {
                downloadBtns += `<a href="/download/${t.task_id}/report" class="btn-download-sm" download>📥 报告</a>`;
            }

            return `
            <div class="task-card" onclick="location.href='#task-${t.task_id}'">
              <div class="task-card-header">
                <span class="task-status-icon">${statusIcon}</span>
                <span class="task-status ${statusClass}">${t.status_text}</span>
              </div>
              <div class="task-msg">${escapeHtml(t.user_message)}</div>
              <div class="task-time">${t.created_at}</div>
              <div class="task-actions">${downloadBtns}</div>
            </div>
          `;
        }).join('');
    } catch (e) {
        console.error('刷新任务列表失败:', e);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
