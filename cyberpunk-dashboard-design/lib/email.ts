import nodemailer from 'nodemailer';

// Initialize transporter with SMTP credentials from environment
export function createEmailTransporter() {
  const smtpHost = process.env.SMTP_HOST;
  const smtpPort = parseInt(process.env.SMTP_PORT || '587', 10);
  const smtpUser = process.env.SMTP_USER;
  const smtpPass = process.env.SMTP_PASS;

  console.log('Creating email transporter with config:', {
    host: smtpHost,
    port: smtpPort,
    user: smtpUser,
    passExists: !!smtpPass,
  });

  if (!smtpHost || !smtpUser || !smtpPass) {
    throw new Error('Missing SMTP configuration in environment variables');
  }

  const transporter = nodemailer.createTransport({
    host: smtpHost,
    port: smtpPort,
    secure: smtpPort === 465, // true for 465, false for other ports (use TLS)
    auth: {
      user: smtpUser,
      pass: smtpPass,
    },
    // Gmail-specific options
    tls: {
      rejectUnauthorized: false, // Allow self-signed certificates if needed
    },
  });

  return transporter;
}

// Get color values based on accent theme
function getAccentColors(accent: string = 'green') {
  const colorMap: Record<string, { primary: string; secondary: string }> = {
    orange: { primary: '#ff6b35', secondary: '#ff9800' },
    green: { primary: '#4ade80', secondary: '#22c55e' },
    blue: { primary: '#3b82f6', secondary: '#0ea5e9' },
  };
  return colorMap[accent] || colorMap['green'];
}

export interface EmailScoreData {
  username: string;
  email: string;
  totalScore: number;
  shots: Array<{ x: number; y: number; score: number }>;
  mode: 'rifle' | 'pistol';
  date?: string;
  averageScore?: number;
  imageBase64?: string; // Base64 encoded image
  accent?: 'orange' | 'green' | 'blue';
}

export async function sendScoreEmail(scoreData: EmailScoreData) {
  try {
    console.log('[sendScoreEmail] Starting email send for:', scoreData.email);
    
    const transporter = createEmailTransporter();
    const colors = getAccentColors(scoreData.accent || 'green');

    const shotsList = scoreData.shots
      .map(
        (shot, index) =>
          `<tr>
            <td style="padding: 8px; border: 1px solid #333;">${index + 1}</td>
            <td style="padding: 8px; border: 1px solid #333;">${shot.score.toFixed(2)}</td>
            <td style="padding: 8px; border: 1px solid #333;">X: ${shot.x.toFixed(1)}, Y: ${shot.y.toFixed(1)}</td>
          </tr>`
      )
      .join('');

    const averageScore = scoreData.averageScore || 
      (scoreData.shots.length > 0
        ? scoreData.shots.reduce((sum, shot) => sum + shot.score, 0) / scoreData.shots.length
        : 0);

    // Build target image HTML if base64 is provided
    const targetImageHTML = scoreData.imageBase64
      ? `
        <div style="text-align: center; margin: 25px 0;">
          <h3 style="color: ${colors.primary}; margin: 0 0 15px 0;">Target Image</h3>
          <img src="data:image/png;base64,${scoreData.imageBase64}" alt="Target" style="max-width: 100%; height: auto; border: 3px solid ${colors.primary}; border-radius: 8px; display: inline-block;" />
        </div>
      `
      : '';

    const htmlContent = `
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body { font-family: Arial, sans-serif; background-color: #0f0f0f; color: #fff; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; background-color: #1a1a1a; padding: 30px; border-radius: 8px; border: 2px solid ${colors.primary}; }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: ${colors.primary}; font-size: 28px; margin: 0; }
        .header p { color: #999; margin: 10px 0 0 0; }
        .score-card { background-color: #2a2a2a; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid ${colors.primary}; }
        .score-info { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }
        .score-item { background-color: #2a2a2a; padding: 15px; border-radius: 6px; text-align: center; }
        .score-item .label { color: #999; font-size: 12px; text-transform: uppercase; }
        .score-item .value { color: ${colors.primary}; font-size: 28px; font-weight: bold; margin-top: 10px; }
        .mode { color: ${colors.secondary}; font-size: 14px; margin-top: 5px; text-transform: uppercase; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        table th { background-color: ${colors.primary}; color: #000; padding: 10px; text-align: left; }
        table tr:nth-child(even) { background-color: #232323; }
        .footer { text-align: center; margin-top: 30px; color: #666; font-size: 12px; }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>🎯 LAKSHYA - Score Report</h1>
          <p>${scoreData.date || new Date().toLocaleDateString()}</p>
        </div>

        <div class="score-card">
          <div class="score-info">
            <div class="score-item">
              <div class="label">Total Score</div>
              <div class="value">${scoreData.totalScore.toFixed(2)}</div>
            </div>
            <div class="score-item">
              <div class="label">Average Score</div>
              <div class="value">${averageScore.toFixed(2)}</div>
            </div>
            <div class="score-item">
              <div class="label">Shots Fired</div>
              <div class="value">${scoreData.shots.length}</div>
              <div class="mode">${scoreData.mode.toUpperCase()}</div>
            </div>
            <div class="score-item">
              <div class="label">Status</div>
              <div class="value" style="color: ${colors.secondary};">✓ Complete</div>
            </div>
          </div>
        </div>

        ${targetImageHTML}

        <h3 style="color: ${colors.primary}; margin-top: 30px;">Shot Details</h3>
        <table>
          <thead>
            <tr>
              <th>Shot #</th>
              <th>Score</th>
              <th>Position</th>
            </tr>
          </thead>
          <tbody>
            ${shotsList}
          </tbody>
        </table>

        <div class="footer">
          <p>This is an automated report from LAKSHYA Target Practice System</p>
          <p>© 2026 LAKSHYA. All rights reserved.</p>
        </div>
      </div>
    </body>
    </html>
    `;

    const mailOptions = {
      from: process.env.SMTP_USER || 'noreply@lakshya.local',
      to: scoreData.email,
      subject: `🎯 LAKSHYA Score Report - ${scoreData.mode.toUpperCase()} - ${scoreData.totalScore.toFixed(2)} Points`,
      html: htmlContent,
    };

    console.log('[sendScoreEmail] Mail options:', {
      from: mailOptions.from,
      to: mailOptions.to,
      subject: mailOptions.subject,
    });

    const info = await transporter.sendMail(mailOptions);
    console.log('[sendScoreEmail] Email sent successfully:', info.response);
    return { success: true, message: 'Email sent successfully', messageId: info.messageId };
  } catch (error) {
    console.error('[sendScoreEmail] Error:', error);
    throw error;
  }
}

export async function sendWrapEmail(wrapData: {
  username: string;
  email: string;
  summary: string;
  stats: {
    totalSessions: number;
    totalShots: number;
    averageScore: number;
    bestScore: number;
  };
  date?: string;
}) {
  try {
    const transporter = createEmailTransporter();

    const htmlContent = `
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body { font-family: Arial, sans-serif; background-color: #0f0f0f; color: #fff; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; background-color: #1a1a1a; padding: 30px; border-radius: 8px; border: 2px solid #ff6b35; }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: #ff6b35; font-size: 28px; margin: 0; }
        .header p { color: #999; margin: 10px 0 0 0; }
        .wrap-card { background-color: #2a2a2a; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #4ade80; }
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }
        .stat-item { background-color: #2a2a2a; padding: 15px; border-radius: 6px; text-align: center; }
        .stat-item .label { color: #999; font-size: 12px; text-transform: uppercase; }
        .stat-item .value { color: #4ade80; font-size: 28px; font-weight: bold; margin-top: 10px; }
        .summary-text { background-color: #232323; padding: 15px; border-radius: 6px; line-height: 1.6; margin: 15px 0; }
        .footer { text-align: center; margin-top: 30px; color: #666; font-size: 12px; }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>📊 LAKSHYA - Session Wrap</h1>
          <p>${wrapData.date || new Date().toLocaleDateString()}</p>
        </div>

        <div class="wrap-card">
          <h2 style="color: #4ade80; margin-top: 0;">Your Practice Summary</h2>
          <div class="summary-text">${wrapData.summary}</div>

          <h3 style="color: #ff6b35;">Performance Metrics</h3>
          <div class="stats-grid">
            <div class="stat-item">
              <div class="label">Total Sessions</div>
              <div class="value">${wrapData.stats.totalSessions}</div>
            </div>
            <div class="stat-item">
              <div class="label">Total Shots</div>
              <div class="value">${wrapData.stats.totalShots}</div>
            </div>
            <div class="stat-item">
              <div class="label">Average Score</div>
              <div class="value">${wrapData.stats.averageScore.toFixed(2)}</div>
            </div>
            <div class="stat-item">
              <div class="label">Best Score</div>
              <div class="value">${wrapData.stats.bestScore.toFixed(2)}</div>
            </div>
          </div>
        </div>

        <div class="footer">
          <p>This is an automated report from LAKSHYA Target Practice System</p>
          <p>© 2026 LAKSHYA. All rights reserved.</p>
        </div>
      </div>
    </body>
    </html>
    `;

    const mailOptions = {
      from: process.env.SMTP_USER || 'noreply@lakshya.local',
      to: wrapData.email,
      subject: `📊 LAKSHYA Practice Wrap - ${wrapData.stats.totalSessions} Sessions Summary`,
      html: htmlContent,
    };

    console.log('[sendWrapEmail] Mail options:', {
      from: mailOptions.from,
      to: mailOptions.to,
      subject: mailOptions.subject,
    });

    const info = await transporter.sendMail(mailOptions);
    console.log('[sendWrapEmail] Email sent successfully:', info.response);
    return { success: true, message: 'Wrap email sent successfully', messageId: info.messageId };
  } catch (error) {
    console.error('[sendWrapEmail] Error:', error);
    throw error;
  }
}
